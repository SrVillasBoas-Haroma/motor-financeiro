"""
Regra de aporte do Motor Financeiro.
1) Busca indicadores reais de cada ativo (yfinance), com cache diario.
2) Da uma nota (score) para cada ativo conforme o objetivo da carteira.
3) Transforma a nota em peso-alvo e sugere onde aportar.
Nada aqui e estimado por IA: tudo vem de dados e de regras fixas (config.py).
"""
import base64
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timedelta

from config import CRITERIOS, CONGELADOS, VALOR_MINIMO_APORTE, SEGMENTOS, TETO_SEGMENTO
CACHE_HORAS = 12
CACHE_VERSAO = 4   # mude o numero para forcar o recalculo de todos os indicadores


# ---------------------------------------------------------------- proventos B3
B3_URL = ("https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/"
          "CompanyCall/GetListedSupplementCompany/")
CLASSE_ISIN = {"3": "OR", "4": "PR", "5": "PA", "6": "PB"}


def _proventos_b3(ticker):
    """
    Proventos em dinheiro (dividendos, JCP, rendimentos) do site publico da B3.
    Devolve lista de (data_com, valor_por_acao) so da classe do ticker,
    ou None se a B3 nao tiver dados (ex.: FIIs).
    """
    params = json.dumps({"issuingCompany": ticker[:4], "language": "pt-br"})
    url = B3_URL + base64.b64encode(params.encode()).decode()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        dados = json.loads(r.read().decode("utf-8"))
    if not dados or not isinstance(dados, list):
        return None
    eventos = dados[0].get("cashDividends") or []
    sufixo = ticker[4:]
    saida = []
    for e in eventos:
        isin = e.get("isinCode") or e.get("assetIssued") or ""
        if sufixo == "11":
            if "CDAM" not in isin:          # unit (ex.: TAEE11)
                continue
        elif isin[9:11] != CLASSE_ISIN.get(sufixo, "??"):
            continue
        try:
            data_com = datetime.strptime(e["lastDatePrior"], "%d/%m/%Y")
            valor = float(str(e["rate"]).replace(".", "").replace(",", "."))
        except Exception:
            continue
        saida.append((data_com, valor))
    return saida or None


# ---------------------------------------------------------------- indicadores
def _calcular_indicadores(ticker):
    import yfinance as yf

    tk = yf.Ticker(ticker + ".SA")
    ind = {"ticker": ticker, "atualizado_em": datetime.now().isoformat(timespec="minutes")}

    hist = tk.history(period="1y", interval="1d", auto_adjust=False)
    if hist is not None and len(hist) > 20:
        close = hist["Close"].dropna()
        # remove erros de dado do Yahoo (precos que fogem mais de 30% da mediana dos vizinhos)
        mediana = close.rolling(5, center=True, min_periods=1).median()
        close = close[(close / mediana - 1).abs() < 0.30]
        preco = float(close.iloc[-1])
        ret = close.pct_change().dropna()
        ret = ret[ret.abs() < 0.25]      # descarta saltos irreais de um dia (erro de dado)
        ind["volatilidade"] = round(float(ret.std() * math.sqrt(252)) * 100, 2)      # % ao ano
        ind["retorno_12m"] = round((preco / float(close.iloc[0]) - 1) * 100, 2)        # %
        ind["dist_max_52s"] = round((preco / float(close.max()) - 1) * 100, 2)         # % abaixo da maxima
    else:
        preco = None

    # proventos: B3 para acoes/units (oficial); Yahoo para FIIs
    agora = datetime.now()
    b3 = None
    try:
        b3 = _proventos_b3(ticker)
    except Exception as e:
        ind["erro_b3"] = str(e)[:120]
    datas_yahoo = []
    div = None
    try:
        div = tk.dividends
        if div is not None and len(div):
            div.index = div.index.tz_localize(None) if div.index.tz is not None else div.index
            datas_yahoo = list(div.index.to_pydatetime())
    except Exception:
        div = None

    if b3:
        ind["fonte_proventos"] = "B3"
        ultimo_ano = sum(v for d, v in b3 if agora - timedelta(days=365) <= d <= agora)
        if preco:
            ind["dy_12m"] = round(ultimo_ano / preco * 100, 2)
        # regularidade: anos (dos ultimos 5 completos) com algum provento
        anos = {d.year for d, _ in b3} | {d.year for d in datas_yahoo}
        ultimos5 = range(agora.year - 5, agora.year)
        ind["consistencia_div"] = round(100 * sum(1 for a in ultimos5 if a in anos) / 5, 1)
        ind["criterio_constancia"] = "anos com provento (ultimos 5)"
    elif div is not None and len(div):
        ind["fonte_proventos"] = "Yahoo"
        ultimo_ano = div[div.index >= agora - timedelta(days=365)]
        if preco:
            ind["dy_12m"] = round(float(ultimo_ano.sum()) / preco * 100, 2)
        dois_anos = div[div.index >= agora - timedelta(days=730)]
        meses = {(d.year, d.month) for d in dois_anos.index}
        ind["consistencia_div"] = round(len(meses) / 24 * 100, 1)
        ind["criterio_constancia"] = "meses com provento (ultimos 24)"
    else:
        ind["fonte_proventos"] = "nenhuma"
        ind["dy_12m"] = 0.0
        ind["consistencia_div"] = 0.0

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
        if c and c.get("_v") == CACHE_VERSAO and time.time() - c.get("_ts", 0) < CACHE_HORAS * 3600:
            continue
        try:
            ind = _calcular_indicadores(t)
            ind["_ts"] = time.time()
            ind["_v"] = CACHE_VERSAO
            cache[t] = ind
            mudou = True
        except Exception as e:
            cache.setdefault(t, {"ticker": t, "erro": str(e)})
    if mudou:
        os.makedirs(data_dir, exist_ok=True)
        json.dump(cache, open(arq, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return {t: {k: v for k, v in cache.get(t, {}).items() if not k.startswith("_")} for t in tickers}


# ---------------------------------------------------------------- notas
# Criterios que ja sao uma porcentagem de 0 a 100 (nao comparam por ranking)
ESCALA_ABSOLUTA = {"consistencia_div"}

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
            if crit in ESCALA_ABSOLUTA:   # ja vem de 0 a 100: usa o proprio valor
                p = max(0.0, min(1.0, valores[crit][t] / 100))
            else:
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
                                       if k in CRITERIOS[carteira] or k in ("setor", "dy_12m", "fonte_proventos")},
                       "comprar_qtd": 0})

    # ---- diversificacao por segmento
    tetos = TETO_SEGMENTO.get(carteira, {})
    base_total = sum(a["valor"] for a in ativos) + valor_aporte      # carteira inteira apos o aporte
    seg_atual = {}
    for a in ativos:
        sg = SEGMENTOS.get(a["ticker"], "outros")
        seg_atual[sg] = seg_atual.get(sg, 0) + a["valor"]
    espaco = {sg: tetos.get(sg, tetos.get("padrao", 100)) / 100 * base_total - v
              for sg, v in seg_atual.items()}
    for l in linhas:
        l["segmento"] = SEGMENTOS.get(l["ticker"], "outros")
        l["bloqueado_segmento"] = espaco.get(l["segmento"], 0) <= 0

    # escolhe os mais abaixo do alvo, fora de segmentos que ja estouraram o teto
    livres = [l for l in linhas if not l["bloqueado_segmento"]]
    candidatos = sorted([l for l in livres if l["falta_para_alvo"] > 0],
                        key=lambda l: -l["falta_para_alvo"])[:max_ativos]
    if not candidatos:
        candidatos = sorted(livres, key=lambda l: -l["peso_alvo_pct"])[:max_ativos]
    soma_falta = sum(max(l["falta_para_alvo"], 0) for l in candidatos) or 1
    usado_seg = {}
    for l in candidatos:
        parte = valor_aporte * max(l["falta_para_alvo"], 0) / soma_falta
        sg = l["segmento"]
        parte = min(parte, max(espaco.get(sg, 0) - usado_seg.get(sg, 0), 0))
        l["comprar_qtd"] = int(parte // l["preco"])
        usado_seg[sg] = usado_seg.get(sg, 0) + l["comprar_qtd"] * l["preco"]

    # sobra: compra 1 unidade de quem ainda esta mais longe do alvo, cabe no saldo e no teto
    gasto = sum(l["comprar_qtd"] * l["preco"] for l in candidatos)
    sobra = valor_aporte - gasto
    while True:
        cabe = [l for l in candidatos if l["preco"] <= sobra
                and usado_seg.get(l["segmento"], 0) + l["preco"] <= espaco.get(l["segmento"], 0)]
        if not cabe:
            break
        l = max(cabe, key=lambda x: x["falta_para_alvo"] - x["comprar_qtd"] * x["preco"])
        l["comprar_qtd"] += 1
        sobra -= l["preco"]
        usado_seg[l["segmento"]] = usado_seg.get(l["segmento"], 0) + l["preco"]

    segmentos = []
    for sg in sorted(set(seg_atual) | set(usado_seg)):
        teto = tetos.get(sg, tetos.get("padrao", 100))
        antes = seg_atual.get(sg, 0)
        depois = antes + usado_seg.get(sg, 0)
        segmentos.append({"segmento": sg, "teto_pct": teto,
                          "atual_pct": round(100 * antes / (base_total - valor_aporte), 2),
                          "depois_pct": round(100 * depois / base_total, 2),
                          "acima_do_teto": espaco.get(sg, 0) <= 0})
    segmentos.sort(key=lambda x: -x["depois_pct"])

    compras = []
    for l in candidatos:
        if l["comprar_qtd"] <= 0:
            continue
        valor = round(l["comprar_qtd"] * l["preco"], 2)
        novo = l["valor_atual"] + valor
        compras.append({"ticker": l["ticker"], "segmento": l["segmento"],
                        "comprar_qtd": l["comprar_qtd"], "preco": l["preco"],
                        "cotacao_em": l["cotacao_em"], "valor": valor,
                        "peso_atual_pct": l["peso_atual_pct"],
                        "peso_depois_pct": round(100 * novo / valor_novo, 2),
                        "peso_alvo_pct": l["peso_alvo_pct"], "nota": l["nota"],
                        "indicadores": l["indicadores"]})
    compras.sort(key=lambda c: -c["valor"])

    return {"carteira": carteira, "valor_aporte": valor_aporte,
            "valor_usado": round(valor_aporte - sobra, 2), "sobra": round(sobra, 2),
            "compras": compras,
            "segmentos": segmentos,
            "ranking": sorted(linhas, key=lambda l: -l["nota"]),
            "congelados": [{"ticker": c["ticker"], "valor": c["valor"], "motivo": c["motivo"]} for c in congelados],
            "regra": "peso-alvo proporcional a (0.5 + nota/100); aporte nos mais abaixo do alvo, "
                     "respeitando o teto de cada segmento; quantidades inteiras com o preco atual",
            "aviso": "Apoio a decisao para uso pessoal. Nao e recomendacao de investimento."}
