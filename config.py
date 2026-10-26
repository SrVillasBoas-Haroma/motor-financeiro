# Configuracao das carteiras (sem dados pessoais - pode ficar no GitHub).
# Os numeros das contas ficam nas variaveis CONTA_ALPHA e CONTA_PRIME do Coolify.

CARTEIRAS = {
    "alpha": {"nome": "Alpha", "corretora": "Rico", "objetivo": "Crescimento de patrimonio"},
    "prime": {"nome": "Prime", "corretora": "XP", "objetivo": "Renda passiva mensal"},
}

RENDA_FIXA = {
    "nome": "Renda Fixa",
    "corretora": "Rico",
    "tipo": "investimento",
    "alvo_pct_patrimonio_total": 20,
}

# ---------------------------------------------------------------- regra de aporte
# Criterios da nota de cada carteira: "indicador": (peso, maior_e_melhor)
#   dy_12m           dividend yield dos ultimos 12 meses (%)
#   consistencia_div % dos ultimos 24 meses com provento pago
#   volatilidade     oscilacao anual do preco (%) - menor e melhor
#   retorno_12m      valorizacao do preco em 12 meses (%)
#   roe              retorno sobre o patrimonio (%)
#   p_l              preco / lucro - menor e melhor
#   p_vp             preco / valor patrimonial - menor e melhor
CRITERIOS = {
    "prime": {   # renda passiva mensal
        "dy_12m": (40, True),
        "consistencia_div": (25, True),
        "volatilidade": (20, False),
        "p_vp": (15, False),
    },
    "alpha": {   # crescimento de patrimonio
        "roe": (25, True),
        "p_l": (20, False),
        "retorno_12m": (20, True),
        "dy_12m": (20, True),
        "volatilidade": (15, False),
    },
}

# Ativos que nao recebem aporte (so mantem a posicao)
CONGELADOS = ["AMER3"]

# Posicoes abaixo deste valor (R$) nao recebem aporte ate voce decidir
VALOR_MINIMO_APORTE = 130

# ---------------------------------------------------------------- diversificacao
# Segmento de cada ativo (revise e ajuste quando quiser)
SEGMENTOS = {
    # acoes
    "BBAS3": "financeiro", "BBDC4": "financeiro", "BBSE3": "financeiro", "CXSE3": "financeiro",
    "ITSA4": "financeiro", "SANB11": "financeiro",
    "CMIG4": "energia_eletrica", "CPLE3": "energia_eletrica", "EGIE3": "energia_eletrica",
    "ENGI11": "energia_eletrica", "TAEE11": "energia_eletrica", "TAEE4": "energia_eletrica",
    "PETR4": "petroleo",
    "SAPR4": "saneamento",
    "CURY3": "construcao", "DIRR3": "construcao", "TEND3": "construcao",
    "GOAU3": "materiais_basicos", "KLBN4": "materiais_basicos", "RANI3": "materiais_basicos",
    "MBRF3": "alimentos", "AGRO3": "agro",
    "ALOS3": "shoppings", "IGTI11": "shoppings",
    "RENT3": "locacao", "AMER3": "varejo",
    # fundos
    "MXRF11": "fii_papel", "KNSC11": "fii_papel", "CYCR11": "fii_papel", "VGHF11": "fii_papel",
    "VSLH11": "fii_papel", "VRTA11": "fii_papel", "RECR11": "fii_papel",
    "BTLG11": "fii_tijolo", "XPML11": "fii_tijolo", "HGLG11": "fii_tijolo",
    "SNAG11": "fiagro",
}

# Teto de cada segmento dentro da carteira (% do valor da carteira).
# "padrao" vale para qualquer segmento nao listado.
TETO_SEGMENTO = {
    "prime": {"padrao": 30, "financeiro": 30, "fii_papel": 35, "fii_tijolo": 35},
    "alpha": {"padrao": 25},
}

# ---------------------------------------------------------------- radar de oportunidades
# Universo de ativos que o radar avalia (fora da sua carteira). Edite a vontade.
RADAR_UNIVERSO = {
    "alpha": [   # acoes para crescimento
        "ITUB4", "BPAC11", "ABCB4", "B3SA3", "PSSA3", "WEGE3", "VALE3", "SUZB3", "PRIO3",
        "SBSP3", "CSMG3", "EQTL3", "CPFE3", "ALUP11", "VIVT3", "TIMS3", "ABEV3", "RADL3",
        "LREN3", "MDIA3", "SLCE3", "RAIL3", "EMBR3", "TOTS3", "KLBN11", "CMIN3",
    ],
    "prime": [   # pagadoras e FIIs para renda
        "KNRI11", "VISC11", "XPLG11", "HGRU11", "PVBI11", "TRXF11", "HGCR11", "KNCR11",
        "KNIP11", "CPTS11", "RBRR11", "MCCI11", "JSRE11", "ITUB4", "BBDC3", "ABCB4",
        "TAEE11", "ALUP11", "CPFE3", "VIVT3", "PSSA3", "SAPR11", "CSMG3", "ISAE4",
    ],
}

SEGMENTOS.update({
    "ITUB4": "financeiro", "BPAC11": "financeiro", "ABCB4": "financeiro", "B3SA3": "financeiro",
    "PSSA3": "financeiro", "BBDC3": "financeiro",
    "WEGE3": "industria", "EMBR3": "industria", "RAIL3": "logistica", "TOTS3": "tecnologia",
    "VALE3": "materiais_basicos", "SUZB3": "materiais_basicos", "KLBN11": "materiais_basicos",
    "CMIN3": "materiais_basicos", "PRIO3": "petroleo",
    "SBSP3": "saneamento", "CSMG3": "saneamento", "SAPR11": "saneamento",
    "EQTL3": "energia_eletrica", "CPFE3": "energia_eletrica", "ALUP11": "energia_eletrica",
    "ISAE4": "energia_eletrica",
    "VIVT3": "telecom", "TIMS3": "telecom", "ABEV3": "bebidas", "RADL3": "saude",
    "LREN3": "varejo", "MDIA3": "alimentos", "SLCE3": "agro",
    "KNRI11": "fii_tijolo", "VISC11": "fii_tijolo", "XPLG11": "fii_tijolo", "HGRU11": "fii_tijolo",
    "PVBI11": "fii_tijolo", "TRXF11": "fii_tijolo", "JSRE11": "fii_tijolo",
    "HGCR11": "fii_papel", "KNCR11": "fii_papel", "KNIP11": "fii_papel", "CPTS11": "fii_papel",
    "RBRR11": "fii_papel", "MCCI11": "fii_papel",
})
