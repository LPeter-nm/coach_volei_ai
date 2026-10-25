"""
Backend FastAPI - expoe o motor de IA (Coach Volei) como um endpoint
HTTP. Esta e' a camada que o Render hospeda, e que a Evolution API
chama quando uma mensagem chega no WhatsApp.
"""

import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Request
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

# --- Configuracao especifica da Evolution API (so' usada pelo /webhook) ---
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")       # ex: https://sua-evolution.com
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE")     # nome da instancia no WhatsApp
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")        # apikey pra ENVIAR mensagens
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")               # token que so' nos e a Evolution conhecemos

# Guarda, pra cada numero de telefone, o id da ultima resposta da IA.
# Isso mantem o contexto da conversa por pessoa. E' em memoria (RAM):
# some se o servidor reiniciar. Quando chegar a vez do Supabase, isso
# vira persistente.
conversas_por_numero: dict[str, str] = {}

# Lista opcional de numeros autorizados a falar com o bot, separados por
# virgula no .env (ex: "5586999990000,5586988880000"). Se ficar vazia,
# o bot responde a qualquer numero que mandar mensagem.
_numeros_env = os.getenv("ALLOWED_NUMBERS", "")
ALLOWED_NUMBERS = {n.strip() for n in _numeros_env.split(",") if n.strip()}

app = FastAPI(title="Coach Volei - API")


class ChatRequest(BaseModel):
    mensagem: str
    previous_interaction_id: str | None = None


class ChatResponse(BaseModel):
    resposta: str
    interaction_id: str


def perguntar_ao_coach(mensagem: str, previous_interaction_id: str | None):
    """Logica compartilhada: manda uma mensagem pro Gemini com a persona
    do Coach Volei e devolve (texto_da_resposta, id_da_interacao).
    Usada tanto pelo /chat (teste manual) quanto pelo /webhook (WhatsApp)."""
    interaction = client.interactions.create(
        model=MODEL,
        system_instruction=SYSTEM_PROMPT,
        input=mensagem,
        previous_interaction_id=previous_interaction_id,
    )
    resposta = interaction.steps[-1].content[0].text # type: ignore
    return resposta, interaction.id # type: ignore


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
        resposta, interaction_id = perguntar_ao_coach(mensagem, request.previous_interaction_id)
    except Exception:
        # Nao repassamos o erro original pro cliente: evita vazar
        # detalhes internos (como pedacos de stack trace) pra fora.
        raise HTTPException(status_code=502, detail="Erro ao consultar o modelo de IA.")

    return ChatResponse(resposta=resposta, interaction_id=interaction_id) # type: ignore


@app.post("/webhook")
async def webhook(request: Request, authorization: str | None = Header(default=None)):
    # 1) Confere se quem chamou realmente conhece o nosso segredo.
    # Sem isso, qualquer pessoa na internet que descobrisse esse
    # endereco poderia mandar mensagens falsas pro nosso sistema.
    if WEBHOOK_SECRET and authorization != f"Bearer {WEBHOOK_SECRET}":
        raise HTTPException(status_code=401, detail="Nao autorizado.")

    body = await request.json()

    # A Evolution API ja' manda varios tipos de evento (conexao, status
    # de leitura, etc). So' nos interessa "chegou mensagem nova".
    evento = (body.get("event") or "").upper().replace(".", "_")
    if evento != "MESSAGES_UPSERT":
        return {"status": "ignorado", "motivo": "evento nao tratado"}

    data = body.get("data", {})

    # fromMe = True significa que fomos NOS que mandamos essa mensagem
    # (ex: voce mesmo testando pelo celular). Se processarmos isso, a
    # IA entraria num loop respondendo pra si mesma.
    if data.get("key", {}).get("fromMe"):
        return {"status": "ignorado", "motivo": "mensagem propria"}

    # O texto pode vir em lugares diferentes dependendo do tipo de
    # mensagem (conversa simples vs mensagem com preview de link etc).
    mensagem_texto = (
        data.get("message", {}).get("conversation")
        or data.get("message", {}).get("extendedTextMessage", {}).get("text")
    )
    if not mensagem_texto:
        return {"status": "ignorado", "motivo": "sem texto (ex: audio ou imagem)"}

    if len(mensagem_texto) > MAX_CARACTERES:
        mensagem_texto = mensagem_texto[:MAX_CARACTERES]

    # remoteJid vem como "5511999999999@s.whatsapp.net" - pegamos so'
    # o numero, que e' o que a Evolution API espera de volta pra enviar.
    remote_jid = data.get("key", {}).get("remoteJid", "")
    numero = remote_jid.split("@")[0]

    # Se a lista estiver preenchida, so' deixa passar quem esta' nela.
    # Isso roda ANTES de gastar qualquer chamada na API da Gemini.
    if ALLOWED_NUMBERS and numero not in ALLOWED_NUMBERS:
        return {"status": "ignorado", "motivo": "numero fora da lista permitida"}

    previous_id = conversas_por_numero.get(numero)

    try:
        resposta_texto, interaction_id = perguntar_ao_coach(mensagem_texto, previous_id)
    except Exception:
        return {"status": "erro", "motivo": "falha ao consultar a IA"}

    conversas_por_numero[numero] = interaction_id # type: ignore

    # Agora enviamos a resposta de volta, chamando a propria Evolution
    # API - diferente do /chat, aqui ninguem fica esperando a resposta
    # no mesmo lugar que perguntou; precisamos "ligar de volta".
    url_envio = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    async with httpx.AsyncClient(timeout=30) as http_client:
        await http_client.post(
            url_envio,
            headers={"apikey": EVOLUTION_API_KEY}, # type: ignore
            json={"number": numero, "text": resposta_texto},
        )

    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}