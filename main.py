"""
Backend FastAPI - expoe o motor de IA (Coach Volei) como um endpoint
HTTP. Esta e' a camada que o Render vai hospedar, e que a Evolution
API vai chamar quando uma mensagem chegar no WhatsApp.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google import genai

from persona import SYSTEM_PROMPT

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY nao definida. Configure o .env.")

client = genai.Client(api_key=API_KEY)
MODEL = "gemini-3-flash-preview"
MAX_CARACTERES = 500

app = FastAPI(title="Coach Volei - API")


class ChatRequest(BaseModel):
    mensagem: str
    previous_interaction_id: str | None = None


class ChatResponse(BaseModel):
    resposta: str
    interaction_id: str


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    mensagem = request.mensagem.strip()

    if not mensagem:
        raise HTTPException(status_code=400, detail="Mensagem vazia.")
    if len(mensagem) > MAX_CARACTERES:
        raise HTTPException(
            status_code=400,
            detail=f"Mensagem acima do limite de {MAX_CARACTERES} caracteres.",
        )

    try:
        interaction = client.interactions.create(
            model=MODEL,
            system_instruction=SYSTEM_PROMPT,
            input=mensagem,
            previous_interaction_id=request.previous_interaction_id,
        )
    except Exception:
        # Nao repassamos o erro original pro cliente: evita vazar
        # detalhes internos (como pedacos de stack trace) pra fora.
        raise HTTPException(status_code=502, detail="Erro ao consultar o modelo de IA.")

    resposta = interaction.steps[-1].content[0].text
    return ChatResponse(resposta=resposta, interaction_id=interaction.id)


@app.get("/health")
def health():
    return {"status": "ok"}