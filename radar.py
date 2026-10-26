"""
Radar de oportunidades: avalia ativos FORA da sua carteira com os mesmos
criterios e dados da regra de aporte, e mostra os melhores para voce estudar.
Nada e comprado ou adicionado automaticamente: a decisao e sempre sua.
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException

import aporte
from config import CARTEIRAS, CRITERIOS, RADAR_UNIVERSO, SEGMENTOS, TETO_SEGMENTO
from main import DATA_DIR, agora, autorizado, carteiras as ver_carteiras

router = APIRouter()


def _indicadores_rapido(tickers):
    """Busca os indicadores em paralelo (8 de cada vez) e grava no mesmo cache da regra de aporte."""
    arq = os.path.join(DATA_DIR, "indicadores.json")
    try:
        cache = json.load(open(arq, encoding="utf-8"))
    except Exception:
        cache = {}
    faltam = [t for t in tickers
              if not (cache.get(t, {}).get("_v") == aporte.CACHE_VERSAO
                      and time.time() - cache[t].get("_ts", 0) < aporte.CACHE_HORAS * 3600)]

    def buscar(t):
        try:
            ind = aporte._calcular_indicadores(t)
            ind["_ts"], ind["_v"] = time.time(), aporte.CACHE_VERSAO
            return t, ind
        except Exception as e:
            return t, {"ticker": t, "erro": str(e)[:120]}

    if faltam:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for t, ind in pool.map(buscar, faltam):
                cache[t] = ind
        os.makedirs(DATA_DIR, exist_ok=True)
        json.dump(cache, open(arq, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return {t: {k: v for k, v in cache.get(t, {}).items() if not k.startswith("_")} for t in tickers}


def _motivos(det, ind):
    """Frase curta com os pontos fortes do ativo (criterios com nota >= 70)."""
    nomes = {"dy_12m": "dividend yield", "consistencia_div": "constancia de proventos",
             "volatilidade": "baixa volatilidade", "p_vp": "P/VP baixo", "roe": "ROE alto",
             "p_l": "P/L baixo", "retorno_12m": "valorizacao em 12 meses"}
    fortes = [nomes.get(c, c) for c, n in sorted(det.items(), key=lambda x: -(x[1] or 0)) if n is not None and n >= 70]
    return ", ".join(fortes[:3]) or "sem destaque claro"


@router.get("/radar/{carteira}", dependencies=[Depends(autorizado)])
def radar(carteira: str, limite: int = 10):
    c = carteira.strip().lower()
    if c not in CARTEIRAS:
        raise HTTPException(400, "carteira invalida (use alpha ou prime)")

    visao = ver_carteiras()
    possuidos = {a["ticker"] for cart in visao["carteiras"].values() for a in cart["ativos"]}
    meus = [a["ticker"] for a in visao["carteiras"].get(c, {}).get("ativos", [])]
    candidatos = [t for t in RADAR_UNIVERSO.get(c, []) if t not in possuidos]
    if not candidatos:
        return {"carteira": c, "oportunidades": [], "aviso": "universo do radar vazio ou todo ja na carteira"}

    inds = _indicadores_rapido(meus + candidatos)
    validos = {t: i for t, i in inds.items() if "erro" not in i and i.get("volatilidade") is not None}
    nt = aporte.notas(c, validos)                       # compara candidatos COM os seus ativos

    notas_meus = sorted(nt[t]["nota"] for t in meus if t in nt)
    mediana = notas_meus[len(notas_meus) // 2] if notas_meus else 50

    # peso atual de cada segmento na carteira
    valor_c = visao["carteiras"].get(c, {}).get("valor", 0) or 1
    seg_pct = {}
    for a in visao["carteiras"].get(c, {}).get("ativos", []):
        sg = SEGMENTOS.get(a["ticker"], "outros")
        seg_pct[sg] = seg_pct.get(sg, 0) + 100 * a["valor"] / valor_c
    tetos = TETO_SEGMENTO.get(c, {})

    lista, ignorados = [], []
    for t in candidatos:
        if t not in nt:
            ignorados.append({"ticker": t, "motivo": inds.get(t, {}).get("erro", "sem dados suficientes")})
            continue
        sg = SEGMENTOS.get(t, "outros")
        teto = tetos.get(sg, tetos.get("padrao", 100))
        lista.append({"ticker": t, "segmento": sg, "nota": nt[t]["nota"],
                      "acima_da_mediana_da_carteira": nt[t]["nota"] >= mediana,
                      "segmento_na_carteira_pct": round(seg_pct.get(sg, 0), 2), "teto_segmento_pct": teto,
                      "segmento_lotado": seg_pct.get(sg, 0) >= teto,
                      "pontos_fortes": _motivos(nt[t]["por_criterio"], validos[t]),
                      "notas_por_criterio": nt[t]["por_criterio"],
                      "indicadores": {k: v for k, v in validos[t].items()
                                      if k in CRITERIOS[c] or k in ("setor", "dy_12m", "fonte_proventos")}})
    lista.sort(key=lambda x: (x["segmento_lotado"], -x["nota"]))
    return {"carteira": c, "objetivo": CARTEIRAS[c]["objetivo"], "gerado_em": agora(),
            "nota_mediana_da_sua_carteira": mediana,
            "oportunidades": lista[:limite], "avaliados": len(lista), "ignorados": ignorados,
            "regra": "mesmos criterios e notas da regra de aporte; candidatos comparados com os seus ativos; "
                     "segmentos ja no teto aparecem por ultimo",
            "aviso": "Lista para ESTUDO. Nao e recomendacao de compra. Nada entra na carteira sem sua decisao."}
