"""
Relatorio com IA para o app.

O app pede (com o login dele) -> o motor chama o fluxo "Motor - Relatorio App" do n8n
-> o n8n busca os numeros no proprio motor, monta o prompt e usa Groq (reserva Gemini)
-> o texto volta para o app.

A chave do n8n fica SO no Coolify (N8N_RELATORIO_URL e N8N_RELATORIO_TOKEN);
o app nunca ve essa chave.
"""
import json
import os
import threading
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from main import agora, autorizado

router = APIRouter()

N8N_URL = os.getenv("N8N_RELATORIO_URL", "")
N8N_TOKEN = os.getenv("N8N_RELATORIO_TOKEN", "")
ESPERA_MAX = 300                  # segundos: o relatorio leva 1-2 min, a reserva pode levar mais
_gerando = threading.Lock()       # um relatorio por vez (evita gastar IA em dobro com clique repetido)


class PedidoRelatorio(BaseModel):
    carteira: str = Field(default="nenhuma", description="nenhuma, alpha ou prime (para incluir sugestao de aporte)")
    valor: float = Field(default=0, ge=0, le=1_000_000, description="valor do aporte em R$ (opcional)")


@router.post("/relatorio", dependencies=[Depends(autorizado)])
def gerar_relatorio(p: PedidoRelatorio):
    if not (N8N_URL and N8N_TOKEN):
        raise HTTPException(503, "relatorio nao configurado no servidor")
    carteira = p.carteira.strip().lower()
    if carteira not in ("nenhuma", "alpha", "prime"):
        raise HTTPException(400, "carteira invalida (use nenhuma, alpha ou prime)")
    valor = round(p.valor, 2) if carteira != "nenhuma" else 0

    if not _gerando.acquire(blocking=False):
        raise HTTPException(429, "ja existe um relatorio sendo gerado. Aguarde ele terminar.")
    try:
        pedido = urllib.request.Request(
            N8N_URL, method="POST",
            data=json.dumps({"carteira": carteira, "valor": valor}).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-relatorio-token": N8N_TOKEN},
        )
        try:
            with urllib.request.urlopen(pedido, timeout=ESPERA_MAX) as resp:
                dados = json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raise HTTPException(502, f"o n8n respondeu com erro {e.code}")
        except (urllib.error.URLError, TimeoutError, OSError):
            raise HTTPException(504, "o n8n nao respondeu a tempo")
        except ValueError:
            raise HTTPException(502, "resposta do n8n em formato inesperado")
    finally:
        _gerando.release()

    if isinstance(dados, list):            # por garantia, se o n8n devolver uma lista
        dados = dados[0] if dados else {}
    texto = (dados or {}).get("texto")
    if not isinstance(texto, str) or not texto.strip():
        raise HTTPException(502, "o n8n nao devolveu o relatorio")
    return {"texto": texto, "ia": dados.get("ia") or "dado nao disponivel",
            "gerado_em": dados.get("gerado_em") or agora(),
            "carteira_aporte": carteira, "valor_aporte": valor,
            "aviso": "Apoio a decisao para uso pessoal. Nao e recomendacao de investimento."}
