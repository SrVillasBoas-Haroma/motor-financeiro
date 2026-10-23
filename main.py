import os
from fastapi import FastAPI, Header, HTTPException

app = FastAPI(title="Motor Financeiro")

TOKEN = os.getenv("API_TOKEN", "")


@app.get("/health")
def health():
    # Rota pública só para saber se o serviço está no ar
    return {"status": "ok"}


@app.get("/teste")
def teste(x_api_token: str = Header(default="")):
    # Rota protegida: só responde se o n8n mandar o token certo
    if not TOKEN or x_api_token != TOKEN:
        raise HTTPException(status_code=401, detail="nao autorizado")
    return {"mensagem": "motor financeiro funcionando"}
