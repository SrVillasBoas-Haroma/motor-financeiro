"""
Acesso do app (Lovable) ao motor:
- login com usuario/senha (variaveis do Coolify) -> chave de sessao de 30 dias
- trava contra tentativas: 5 erros seguidos bloqueiam o login por 15 minutos
- CORS: so o endereco do seu app pode chamar o motor pelo navegador
- o n8n continua usando o API_TOKEN, sem mudanca
- divisao por segmento em /carteiras
"""
import base64
import hashlib
import hmac
import os
import time

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import SEGMENTOS, TETO_SEGMENTO

API_TOKEN = os.getenv("API_TOKEN", "")
APP_USUARIO = os.getenv("APP_USUARIO", "")
APP_SENHA = os.getenv("APP_SENHA", "")
SESSAO_SEGREDO = os.getenv("SESSAO_SEGREDO", "")
SESSAO_DIAS = int(os.getenv("SESSAO_DIAS", "30"))
APP_ORIGENS = [o.strip().rstrip("/") for o in os.getenv("APP_ORIGENS", "").split(",") if o.strip()]

MAX_ERROS, BLOQUEIO_SEG = 5, 15 * 60
_erros = {}          # ip -> (quantidade, primeiro_erro)

router = APIRouter()


# ---------------------------------------------------------------- chave de sessao
def _assinar(texto):
    return hmac.new(SESSAO_SEGREDO.encode(), texto.encode(), hashlib.sha256).hexdigest()


def _criar_sessao(usuario):
    expira = int(time.time()) + SESSAO_DIAS * 86400
    corpo = f"{usuario}|{expira}"
    bruto = f"{corpo}|{_assinar(corpo)}"
    return base64.urlsafe_b64encode(bruto.encode()).decode(), expira


def _sessao_valida(chave):
    if not SESSAO_SEGREDO or not chave:
        return False
    try:
        usuario, expira, assinatura = base64.urlsafe_b64decode(chave.encode()).decode().split("|")
    except Exception:
        return False
    if not hmac.compare_digest(assinatura, _assinar(f"{usuario}|{expira}")):
        return False
    return int(expira) > time.time() and usuario == APP_USUARIO


def autorizado(x_api_token: str = Header(default=""), authorization: str = Header(default="")):
    """Aceita o token do n8n (x-api-token) OU a chave de sessao do app (Authorization: Bearer ...)."""
    if API_TOKEN and hmac.compare_digest(x_api_token, API_TOKEN):
        return
    if authorization.startswith("Bearer ") and _sessao_valida(authorization[7:].strip()):
        return
    raise HTTPException(status_code=401, detail="nao autorizado")


# ---------------------------------------------------------------- login
class Login(BaseModel):
    usuario: str
    senha: str


@router.post("/auth/login")
def login(dados: Login, request: Request):
    if not (APP_USUARIO and APP_SENHA and SESSAO_SEGREDO):
        raise HTTPException(503, "login do app nao configurado no servidor")
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    qtd, inicio = _erros.get(ip, (0, 0))
    if qtd >= MAX_ERROS and time.time() - inicio < BLOQUEIO_SEG:
        faltam = int((BLOQUEIO_SEG - (time.time() - inicio)) // 60) + 1
        raise HTTPException(429, f"muitas tentativas. Tente de novo em {faltam} min")
    ok = hmac.compare_digest(dados.usuario.strip(), APP_USUARIO) and hmac.compare_digest(dados.senha, APP_SENHA)
    if not ok:
        if time.time() - inicio >= BLOQUEIO_SEG:
            qtd, inicio = 0, time.time()
        _erros[ip] = (qtd + 1, inicio or time.time())
        raise HTTPException(401, "usuario ou senha invalidos")
    _erros.pop(ip, None)
    chave, expira = _criar_sessao(APP_USUARIO)
    return {"token": chave, "expira_em": expira, "dias": SESSAO_DIAS}


@router.get("/auth/verificar")
def verificar(authorization: str = Header(default="")):
    ok = authorization.startswith("Bearer ") and _sessao_valida(authorization[7:].strip())
    if not ok:
        raise HTTPException(401, "sessao invalida ou expirada")
    return {"ok": True}


# ---------------------------------------------------------------- segmentos em /carteiras
def adicionar_segmentos(saida):
    """Acrescenta em cada carteira a divisao por segmento e se esta acima do teto."""
    for nome, cart in saida.get("carteiras", {}).items():
        valor = cart.get("valor") or 0
        tetos = TETO_SEGMENTO.get(nome, {})
        soma = {}
        for a in cart.get("ativos", []):
            sg = SEGMENTOS.get(a["ticker"], "outros")
            a["segmento"] = sg
            soma[sg] = soma.get(sg, 0) + a["valor"]
        lista = []
        for sg, v in soma.items():
            teto = tetos.get(sg, tetos.get("padrao", 100))
            pct = round(100 * v / valor, 2) if valor else 0
            lista.append({"segmento": sg, "valor": round(v, 2), "pct": pct, "teto_pct": teto,
                          "acima_do_teto": pct > teto})
        cart["segmentos"] = sorted(lista, key=lambda x: -x["pct"])
    return saida


# ---------------------------------------------------------------- instalar no app
def instalar(app):
    if APP_ORIGENS:
        app.add_middleware(CORSMiddleware, allow_origins=APP_ORIGENS, allow_credentials=False,
                           allow_methods=["GET", "POST", "DELETE"],
                           allow_headers=["Authorization", "Content-Type"])
    app.include_router(router)
