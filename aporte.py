"""
Regra de aporte do Motor Financeiro.
1) Busca indicadores reais de cada ativo (yfinance), com cache diario.
2) Da uma nota (score) para cada ativo conforme o objetivo da carteira.
3) Transforma a nota em peso-alvo e sugere onde aportar.
Nada aqui e estimado por IA: tudo vem de dados e de regras fixas (config.py).
"""
import json
import math
import os
import time
from datetime import datetime, timedelta

from config import CRITERIOS, CONGELADOS, VALOR_MINIMO_APORTE

CACHE_HORAS = 12


# ---------------------------------------------------------------- indicadores
def _calcular_indicadores(ticker):
    import yfinance as yf

    tk = yf.Ticker(ticker + ".SA")
    ind = {"ticker": ticker, "atualizado_em": datetime.now().isoformat(timespec="minutes")}

    hist = tk.history(period="1y", interval="1d", auto_adjust=False)
    if hist is not None and len(hist) > 20:
        close = hist["Close"].dropna()
        preco = float(close.iloc[-1])
        ret = close.pct_change().dropna()
        ind["volatilidade"] = round(float(ret.std() * math.sqrt(252)) * 100, 2)      # % ao ano
        ind["retorno_12m"] = round((preco / float(close.iloc[0]) - 1) * 100, 2)        # %
        ind["dist_max_52s"] = round((preco / float(close.max()) - 1) * 100, 2)         # % abaixo da maxima
    else:
        preco = None

    try:
        div = tk.dividends
        if div is not None and len(div):
            idx = div.index.tz_localize(None) if div.index.tz is not None else div.index
            div.index = idx
            ultimo_ano = div[div.index >= datetime.now() - timedelta(days=365)]
            if preco:
                ind["dy_12m"] = round(float(ultimo_ano.sum()) / preco * 100, 2)        # %
            dois_anos = div[div.index >= datetime.now() - timedelta(days=730)]
            meses = {(d.year, d.month) for d in dois_anos.index}
            ind["consistencia_div"] = round(len(meses) / 24 * 100, 1)                  # % dos meses com provento
        else:
            ind["dy_12m"] = 0.0
            ind["consistencia_div"] = 0.0
    except Exception:
        pass

    try:
        info = tk.info or {}
        if info.get("returnOnEquity") is not None:
            ind["roe"] = round(float(info["returnOnEquity"]) * 100, 2)
        if info.get("trailingPE") is not None:
            ind["p_l"] = round(float(info["trailingPE"]), 2)
        if info.get("priceToBook") is not None:
            ind["p_vp"] = round(float(info["priceToBook"]), 2)
        if info.get("sector"):
            ind["setor"] = info["sector"]
    except Exception:
        pass
    return ind


def indicadores(tickers, data_dir):
    """Indicadores de cada ticker, guardados em cache no /data por CACHE_HORAS."""
    arq = os.path.join(data_dir, "indicadores.json")
    try:
        cache = json.load(open(arq, encoding="utf-8"))
    except Exception:
        cache = {}
    mudou = False
    for t in tickers:
        c = cache.get(t)
        if c and time.time() - c.get("_ts", 0) < CACHE_HORAS * 3600:
            continue
        try:
            ind = _calcular_indicadores(t)
            ind["_ts"] = time.time()
            cache[t] = ind
            mudou = True
        except Exception as e:
            cache.setdefault(t, {"ticker": t, "erro": str(e)})
    if mudou:
        os.makedirs(data_dir, exist_ok=True)
        json.dump(cache, open(arq, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return {t: {k: v for k, v in cache.get(t, {}).items() if k != "_ts"} for t in tickers}


# ---------------------------------------------------------------- notas
def _percentil(valor, todos, maior_melhor):
    """Posicao do ativo entre os da carteira: 1 = melhor, 0 = pior."""
    if len(todos) <= 1:
        return 0.5
    abaixo = sum(1 for v in todos if v < valor)
    iguais = sum(1 for v in todos if v == valor) - 1
    p = (abaixo + iguais / 2) / (len(todos) - 1)
    return p if maior_melhor else 1 - p


def notas(carteira, inds):
    """Nota de 0 a 100 para cada ativo, pelos criterios da carteira (config.py)."""
    criterios = CRITERIOS[carteira]
    valores = {}
    for crit, (peso, maior_melhor) in criterios.items():
        vals = {}
        for t, ind in inds.items():
            v = ind.get(crit)
            if v is None:
                continue
            if crit == "p_l" and v <= 0:      # prejuizo: pior P/L possivel
                v = 10_000
            vals[t] = v
        valores[crit] = vals

    resultado = {}
    for t in inds:
        soma, pesos, detalhe = 0.0, 0.0, {}
        for crit, (peso, maior_melhor) in criterios.items():
            if t not in valores[crit]:
                detalhe[crit] = None
                continue
            p = _percentil(valores[crit][t], list(valores[crit].values()), maior_melhor)
            soma += p * peso
            pesos += peso
            detalhe[crit] = round(p * 100)
        resultado[t] = {"nota": round(100 * soma / pesos, 1) if pesos else 50.0,
                        "criterios_usados": round(100 * pesos / sum(p for p, _ in criterios.values())),
                        "por_criterio": detalhe}
    return resultado


# ---------------------------------------------------------------- sugestao
def sugerir(carteira, valor_aporte, ativos, inds, max_ativos=5):
    """
    ativos: lista vinda de /carteiras (ticker, qtd, preco, valor).
    Regra: peso-alvo proporcional a (0.5 + nota/100); o aporte vai para os
    ativos mais abaixo do alvo, comprando quantidades inteiras.
    """
    congelados, elegiveis = [], []
    for a in ativos:
        if a["ticker"] in CONGELADOS:
            congelados.append({**a, "motivo": "congelado manualmente"})
        elif a["valor"] < VALOR_MINIMO_APORTE:
            congelados.append({**a, "motivo": f"posicao abaixo de R$ {VALOR_MINIMO_APORTE}"})
        else:
            elegiveis.append(a)
    if not elegiveis:
        return {"erro": "nenhum ativo elegivel para aporte"}

    nt = notas(carteira, {a["ticker"]: inds.get(a["ticker"], {}) for a in elegiveis})
    fator = {a["ticker"]: 0.5 + nt[a["ticker"]]["nota"] / 100 for a in elegiveis}
    soma_f = sum(fator.values())
    valor_atual = sum(a["valor"] for a in elegiveis)
    valor_novo = valor_atual + valor_aporte

    linhas = []
    for a in elegiveis:
        alvo_pct = fator[a["ticker"]] / soma_f
        alvo = valor_novo * alvo_pct
        linhas.append({"ticker": a["ticker"], "preco": a["preco"], "cotacao_em": a.get("cotacao_em"),
                       "qtd_atual": a["qtd"], "valor_atual": a["valor"],
                       "peso_atual_pct": round(100 * a["valor"] / valor_atual, 2),
                       "peso_alvo_pct": round(100 * alvo_pct, 2),
                       "falta_para_alvo": round(alvo - a["valor"], 2),
                       "nota": nt[a["ticker"]]["nota"],
                       "notas_por_criterio": nt[a["ticker"]]["por_criterio"],
                       "indicadores": {k: v for k, v in inds.get(a["ticker"], {}).items()
                                       if k in CRITERIOS[carteira] or k in ("setor", "dy_12m")},
                       "comprar_qtd": 0})

    # escolhe os mais abaixo do alvo
    candidatos = sorted([l for l in linhas if l["falta_para_alvo"] > 0],
                        key=lambda l: -l["falta_para_alvo"])[:max_ativos]
    if not candidatos:
        candidatos = sorted(linhas, key=lambda l: -l["peso_alvo_pct"])[:max_ativos]
    soma_falta = sum(max(l["falta_para_alvo"], 0) for l in candidatos) or 1
    for l in candidatos:
        parte = valor_aporte * max(l["falta_para_alvo"], 0) / soma_falta
        l["comprar_qtd"] = int(parte // l["preco"])

    # sobra: compra 1 unidade de quem ainda esta mais longe do alvo e cabe no saldo
    gasto = sum(l["comprar_qtd"] * l["preco"] for l in candidatos)
    sobra = valor_aporte - gasto
    while True:
        cabe = [l for l in candidatos if l["preco"] <= sobra]
        if not cabe:
            break
        l = max(cabe, key=lambda x: x["falta_para_alvo"] - x["comprar_qtd"] * x["preco"])
        l["comprar_qtd"] += 1
        sobra -= l["preco"]

    compras = []
    for l in candidatos:
        if l["comprar_qtd"] <= 0:
            continue
        valor = round(l["comprar_qtd"] * l["preco"], 2)
        novo = l["valor_atual"] + valor
        compras.append({"ticker": l["ticker"], "comprar_qtd": l["comprar_qtd"], "preco": l["preco"],
                        "cotacao_em": l["cotacao_em"], "valor": valor,
                        "peso_atual_pct": l["peso_atual_pct"],
                        "peso_depois_pct": round(100 * novo / valor_novo, 2),
                        "peso_alvo_pct": l["peso_alvo_pct"], "nota": l["nota"],
                        "indicadores": l["indicadores"]})
    compras.sort(key=lambda c: -c["valor"])

    return {"carteira": carteira, "valor_aporte": valor_aporte,
            "valor_usado": round(valor_aporte - sobra, 2), "sobra": round(sobra, 2),
            "compras": compras,
            "ranking": sorted(linhas, key=lambda l: -l["nota"]),
            "congelados": [{"ticker": c["ticker"], "valor": c["valor"], "motivo": c["motivo"]} for c in congelados],
            "regra": "peso-alvo proporcional a (0.5 + nota/100); aporte nos mais abaixo do alvo; "
                     "quantidades inteiras com o preco atual",
            "aviso": "Apoio a decisao para uso pessoal. Nao e recomendacao de investimento."}
