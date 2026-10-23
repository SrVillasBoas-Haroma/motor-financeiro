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
