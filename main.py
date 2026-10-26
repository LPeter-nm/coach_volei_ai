"""
Backend FastAPI - expoe o motor de IA (Coach Volei) como um endpoint
HTTP. Esta e' a camada que o Render hospeda, e que a Evolution API
chama quando uma mensagem chega no WhatsApp.
"""

import asyncio
import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
from google import genai
from supabase import create_client, Client

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

# --- Persistencia do historico de conversa (Supabase) ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # a service_role key, nao a anon/public

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Modo degradado: se o Supabase nao estiver configurado (ex: rodando local
# so' pra testar), caimos de volta pra memoria (RAM) - funciona, mas some
# se o processo reiniciar. Com Supabase configurado, isso nao e' usado.
_conversas_em_memoria: dict[str, str] = {}


def buscar_interaction_id(numero: str) -> str | None:
    """Busca o id da ultima resposta da IA pra esse numero, no Supabase
    (se configurado) ou na memoria (modo degradado)."""
    if not supabase:
        return _conversas_em_memoria.get(numero)

    resultado = (
        supabase.table("conversas")
        .select("interaction_id")
        .eq("numero", numero)
        .limit(1)
        .execute()
    )
    if resultado.data:
        return resultado.data[0]["interaction_id"]
    return None


def salvar_interaction_id(numero: str, interaction_id: str) -> None:
    """Grava/atualiza o id da ultima resposta da IA pra esse numero."""
    if not supabase:
        _conversas_em_memoria[numero] = interaction_id
        return

    # upsert = "atualiza se o numero ja' existir, cria se nao existir"
    supabase.table("conversas").upsert(
        {"numero": numero, "interaction_id": interaction_id}
    ).execute()

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


def perguntar_ao_coach(conteudo, previous_interaction_id: str | None):
    """Logica compartilhada: manda algo pro Gemini com a persona do Coach
    Volei e devolve (texto_da_resposta, id_da_interacao). "conteudo" pode
    ser uma string simples (so' texto) ou uma lista de partes multimodais,
    ex: [{"type": "text", "text": "..."}, {"type": "image", "data": "...", "mime_type": "..."}].
    Usada tanto pelo /chat (teste manual) quanto pelo /webhook (WhatsApp)."""
    interaction = client.interactions.create(
        model=MODEL,
        system_instruction=SYSTEM_PROMPT,
        input=conteudo,
        previous_interaction_id=previous_interaction_id,
    )
    resposta = interaction.steps[-1].content[0].text
    return resposta, interaction.id


async def baixar_midia_evolution(message_key: dict):
    """Baixa o conteudo (base64) de uma midia (imagem/audio) de uma
    mensagem, pedindo pra propria Evolution API - o webhook nunca manda
    o arquivo em si, so' uma referencia a ele. Devolve (base64, mimetype)
    ou (None, None) se falhar."""
    url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
    try:
        async with httpx.AsyncClient(timeout=30) as http_client:
            resposta = await http_client.post(
                url,
                headers={"apikey": EVOLUTION_API_KEY},
                json={"message": {"key": message_key}},
            )
        resposta.raise_for_status()
        corpo = resposta.json()
        return corpo.get("base64"), corpo.get("mimetype")
    except Exception as e:
        print(f"[download midia] falhou: {e}", flush=True)
        return None, None


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

    return ChatResponse(resposta=resposta, interaction_id=interaction_id)


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

    mensagem = data.get("message", {})

    # O texto pode vir em lugares diferentes dependendo do tipo de
    # mensagem (conversa simples vs mensagem com preview de link etc).
    mensagem_texto = mensagem.get("conversation") or mensagem.get("extendedTextMessage", {}).get("text")
    imagem_info = mensagem.get("imageMessage")
    audio_info = mensagem.get("audioMessage")

    if not mensagem_texto and not imagem_info and not audio_info:
        return {"status": "ignorado", "motivo": "tipo de mensagem nao suportado (ex: video, figurinha, documento)"}

    if mensagem_texto and len(mensagem_texto) > MAX_CARACTERES:
        mensagem_texto = mensagem_texto[:MAX_CARACTERES]

    # O WhatsApp as vezes manda um "@lid" (Linked ID, um identificador
    # interno de privacidade) no lugar do numero de telefone real no
    # remoteJid. Quando isso acontece, o numero de verdade costuma vir
    # em outro campo - "senderPn" ou "remoteJidAlt", dependendo da
    # versao da API. Tentamos nessa ordem de prioridade.
    chave = data.get("key", {})
    remote_jid = chave.get("senderPn") or chave.get("remoteJidAlt") or chave.get("remoteJid", "")
    numero = remote_jid.split("@")[0]

    # Log temporario de debug: mostra o numero exato que chegou e a lista
    # configurada, lado a lado, pra confirmar se o formato bate.
    print(f"[filtro numero] recebido={numero!r} remoteJid_original={chave.get('remoteJid')!r} permitidos={ALLOWED_NUMBERS!r}", flush=True)

    # Se a lista estiver preenchida, so' deixa passar quem esta' nela.
    # Isso roda ANTES de gastar qualquer chamada na API da Gemini.
    if ALLOWED_NUMBERS and numero not in ALLOWED_NUMBERS:
        return {"status": "ignorado", "motivo": "numero fora da lista permitida"}

    # O cliente do Supabase e' sincrono (bloqueante); como estamos numa
    # funcao async, rodamos ele numa thread separada pra nao travar o
    # servidor inteiro enquanto espera o banco responder.
    previous_id = await asyncio.to_thread(buscar_interaction_id, numero)

    # Monta o conteudo que vai pra IA: texto puro (caso mais comum), ou
    # uma lista com texto + midia (imagem/audio), dependendo do que chegou.
    if imagem_info or audio_info:
        info_midia = imagem_info or audio_info
        base64_midia, mimetype = await baixar_midia_evolution(chave)
        if not base64_midia:
            return {"status": "erro", "motivo": "falha ao baixar a midia da Evolution API"}

        tipo = "image" if imagem_info else "audio"
        # Legenda da imagem (se a pessoa escreveu algo junto) ou um
        # texto padrao, caso tenha mandado so' a midia, sem nada escrito.
        texto_acompanhando = info_midia.get("caption") or (
            "Descreva o que ha' nessa imagem, relacionando com volei se fizer sentido."
            if tipo == "image"
            else "Ouca esse audio e responda a pergunta, se for sobre volei."
        )
        conteudo = [
            {"type": "text", "text": texto_acompanhando},
            {"type": tipo, "data": base64_midia, "mime_type": mimetype},
        ]
    else:
        conteudo = mensagem_texto

    try:
        resposta_texto, interaction_id = perguntar_ao_coach(conteudo, previous_id)
    except Exception:
        return {"status": "erro", "motivo": "falha ao consultar a IA"}

    await asyncio.to_thread(salvar_interaction_id, numero, interaction_id)

    # Agora enviamos a resposta de volta, chamando a propria Evolution
    # API - diferente do /chat, aqui ninguem fica esperando a resposta
    # no mesmo lugar que perguntou; precisamos "ligar de volta".
    url_envio = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    try:
        async with httpx.AsyncClient(timeout=30) as http_client:
            resposta_envio = await http_client.post(
                url_envio,
                headers={"apikey": EVOLUTION_API_KEY},
                json={"number": numero, "text": resposta_texto},
            )
        # Log temporario de debug: aparece nos logs do Render. Ajuda a ver
        # se a Evolution API aceitou o envio (2xx) ou recusou (4xx/5xx) e
        # por qual motivo, em vez de ficar as cegas.
        print(f"[envio Evolution] status={resposta_envio.status_code} resposta={resposta_envio.text}", flush=True)
    except Exception as e:
        print(f"[envio Evolution] falhou ao chamar a URL: {e}", flush=True)

    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}
