"""
Teste local do "motor" de IA — SEM WhatsApp/Evolution API ainda.

Objetivo deste script: validar que o Python consegue conversar com a
Gemini API (Google AI Studio) usando a persona definida em persona.py.
Essa é a camada mais simples do teste de stack; depois disso entram
FastAPI, Render e Evolution API.

Usa a Interactions API (pacote "google-genai", a mesma que o botão
"Get code" do AI Studio exporta).

Como rodar:
    1. pip install -r requirements.txt
    2. Copie .env.example para .env e preencha GEMINI_API_KEY
       (pegue a chave em https://aistudio.google.com/app/apikey)
    3. python chat_cli.py
"""

# --- IMPORTS: "pegando emprestado" código que outras pessoas já escreveram ---

# "os" é uma biblioteca que já vem instalada no Python (não precisa
# baixar nada). Ela serve pra conversar com o sistema operacional —
# aqui, a gente usa só pra LER variáveis de ambiente (explico já já).
import os

# "sys" também já vem pronta no Python. Usamos ela só por causa da
# função sys.exit(), que encerra o programa imediatamente.
import sys

# "dotenv" é uma biblioteca externa (está no requirements.txt).
# A função load_dotenv() lê o arquivo .env e "carrega" o conteúdo
# dele pra dentro do ambiente do programa, como se você tivesse
# digitado essas variáveis no terminal antes de rodar o script.
from dotenv import load_dotenv

# "genai" é o pacote oficial do Google pra conversar com a Gemini API.
# A sintaxe "from google import genai" significa: dentro do pacote
# "google", existe um sub-pacote chamado "genai" — importe só ele.
from google import genai

# Aqui a gente importa a variável SYSTEM_PROMPT que vive no outro
# arquivo, persona.py. É o Python "colando" o conteúdo daquele
# arquivo pra dentro deste, mas só a parte que a gente pediu.
from persona import SYSTEM_PROMPT


# --- CONFIGURAÇÃO INICIAL: tudo que precisa acontecer ANTES do chat começar ---

# Lê o arquivo .env (se existir) e carrega as variáveis dele.
# Isso precisa rodar ANTES da linha seguinte, senão os.getenv()
# não vai encontrar nada.
load_dotenv()

# os.getenv("GEMINI_API_KEY") procura por uma variável de ambiente
# chamada GEMINI_API_KEY. Se ela existir (porque veio do .env ou foi
# definida no sistema), retorna o valor. Se não existir, retorna None.
API_KEY = os.getenv("GEMINI_API_KEY")

# Aqui a gente verifica: "None" em Python é um jeito de dizer "nada,
# vazio, ausente". A condição "if not API_KEY" é verdadeira quando
# API_KEY é None (ou uma string vazia). Ou seja: "se a chave NÃO foi
# encontrada, faça isto:"
if not API_KEY:
    print("ERRO: variável GEMINI_API_KEY não encontrada.")
    print("Crie um arquivo .env (baseado no .env.example) com sua chave.")
    # sys.exit(1) encerra o programa aqui mesmo. O número 1 é uma
    # convenção que significa "terminei, mas com erro" (0 significaria
    # "terminei com sucesso"). Isso evita que o resto do código rode
    # sem uma chave válida.
    sys.exit(1)

# Cria o "cliente" — um objeto que sabe como se conectar à Gemini API
# usando a chave que a gente acabou de validar. É através dele que
# toda comunicação com o Google vai acontecer daqui pra frente.
client = genai.Client(api_key=API_KEY)

# O nome exato do modelo que você quer usar. Isso precisa bater com
# o que aparecer no botão "Get code" do AI Studio — o Google lança
# modelos novos com frequência, então esse nome pode mudar com o tempo.
MODEL = "gemini-3-flash-preview"

# Um limite simples: se a mensagem do usuário passar disso, a gente
# recusa antes mesmo de gastar uma chamada de API. Evita desperdiçar
# tokens (e dinheiro) com mensagens absurdamente longas.
MAX_CARACTERES = 500


# --- A FUNÇÃO PRINCIPAL: onde a conversa de verdade acontece ---

def main():
    print("🏐 Coach Vôlei — teste local (digite 'sair' para encerrar)\n")

    # A Interactions API não guarda um "histórico de chat" pronto como
    # a versão antiga da API tinha. Em vez disso, CADA resposta recebe
    # um identificador único (um "id"). Se você quer que a próxima
    # pergunta "lembre" do que já foi dito, você precisa passar o id
    # da resposta anterior. Por isso criamos essa variável, começando
    # vazia (None), porque ainda não existe nenhuma resposta anterior.
    previous_id = None

    # "while True" cria um laço que roda PRA SEMPRE — até alguém
    # mandar o programa parar de dentro dele (com "break", mais abaixo).
    # É assim que um chat de terminal fica esperando mensagem após
    # mensagem, sem precisar reiniciar o programa a cada pergunta.
    while True:
        # input() pausa o programa e espera você digitar algo e
        # apertar Enter. .strip() remove espaços em branco acidentais
        # no início/fim do que você digitou (ex: " oi " vira "oi").
        pergunta = input("Você: ").strip()

        # Se a pessoa só apertou Enter sem digitar nada, "pergunta"
        # vira uma string vazia (""), que o Python trata como "falsa".
        # "continue" pula o resto do laço e volta pro início —
        # ou seja, pergunta de novo, sem tentar chamar a IA à toa.
        if not pergunta:
            continue

        # .lower() transforma o texto em minúsculas, pra "Sair", "SAIR"
        # e "sair" serem todos tratados da mesma forma. Se bater com
        # uma dessas três palavras, "break" quebra o "while True" e o
        # programa segue pro que vem depois do laço (nesse caso, o fim).
        if pergunta.lower() in ("sair", "exit", "quit"):
            print("Até a próxima! 🏐")
            break

        # len() conta quantos caracteres tem o texto. Se passar do
        # limite, avisa e usa "continue" pra voltar e pedir de novo,
        # sem gastar uma chamada de API com essa mensagem.
        if len(pergunta) > MAX_CARACTERES:
            print(f"[mensagem muito longa, limite de {MAX_CARACTERES} caracteres]\n")
            continue

        # "try/except" é como o Python lida com "coisas que podem dar
        # errado". O código dentro do "try" roda normalmente; se
        # QUALQUER erro acontecer ali dentro (sem internet, chave
        # inválida, limite de uso excedido etc.), o programa não
        # quebra — ele pula direto pro bloco "except" e continua vivo.
        try:
            # Esta é a chamada de verdade pra Gemini API. Repare nos
            # parâmetros nomeados (model=, system_instruction=...):
            # isso deixa claro o que cada valor representa, em vez de
            # só jogar valores soltos numa ordem que você teria que
            # decorar.
            interaction = client.interactions.create(
                model=MODEL,
                system_instruction=SYSTEM_PROMPT,   # a persona do Coach Vôlei
                input=pergunta,                      # o que você acabou de digitar
                previous_interaction_id=previous_id,  # o "fio da conversa"
            )

            # A resposta vem dentro de uma estrutura meio aninhada:
            # "interaction" tem uma lista de "steps" (passos que o
            # modelo tomou pra gerar a resposta); o ÚLTIMO desses
            # passos ([-1] significa "o último item da lista") é o
            # que tem o texto final. Dentro dele, "content[0].text"
            # pega o texto propriamente dito.
            resposta = interaction.steps[-1].content[0].text

            # f"..." é uma "f-string": permite colocar o valor de uma
            # variável DENTRO de um texto, usando chaves {}.
            print(f"Coach Vôlei: {resposta}\n")

            # Guarda o id dessa resposta. Na PRÓXIMA volta do laço,
            # esse id vai junto na chamada, dizendo pra API "continue
            # a conversa de onde paramos", em vez de começar do zero.
            previous_id = interaction.id

        except Exception as e:
            # "Exception as e" captura qualquer tipo de erro e guarda
            # os detalhes dele na variável "e". Em produção (quando
            # isso virar um webhook público), você NÃO mostraria o
            # erro cru pro usuário final — só registraria num log
            # interno. Aqui, pra teste local, mostrar ajuda a debugar.
            print(f"[erro ao chamar a IA: {e}]\n")


# Isso aqui é um padrão clássico do Python. Ele significa:
# "só rode a função main() se este arquivo foi executado diretamente
# (python chat_cli.py), e NÃO se ele foi apenas importado por outro
# arquivo". Sem essa checagem, se um dia você importar chat_cli.py
# de dentro de outro script, o chat iniciaria sozinho sem você pedir.
if __name__ == "__main__":
    main()
