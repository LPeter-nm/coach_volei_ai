# Teste de stack — Coach Vôlei (motor de IA)

Protótipo mínimo pra validar a camada "Python + Gemini API", antes de
adicionar Evolution API (WhatsApp), Render (hospedagem) e Supabase (banco).

## Como rodar

1. Crie um ambiente virtual (recomendado):
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Copie `.env.example` para `.env` e cole sua chave do Google AI Studio
   (variável `GEMINI_API_KEY`):
   ```bash
   cp .env.example .env
   ```
   Pegue a chave em: https://aistudio.google.com/app/apikey
4. Rode o teste:
   ```bash
   python chat_cli.py
   ```

## Conferindo o modelo

No AI Studio, clique em **"Get code"** (canto superior direito) depois de
testar sua persona. O `model=` que aparecer lá é o nome exato a usar na
constante `MODEL` em `chat_cli.py` — o Google lança modelos novos com
frequência e o nome pode mudar.

## Estrutura

- `persona.py` — define quem é a IA (nome, tom, escopo, regras). Fica
  separado do resto pra facilitar ajustar depois sem mexer na lógica.
- `chat_cli.py` — script de terminal que conversa com a Gemini API usando
  essa persona. É só a camada "cérebro", sem WhatsApp ainda.

## Notas de segurança (valem para esse teste e pro Contaí depois)

- A chave fica **só** no `.env`, que está no `.gitignore` — nunca vai pro
  GitHub. Se em algum momento ela for exposta (ex: commitada sem querer),
  revogue e gere uma nova em https://aistudio.google.com/app/apikey.
- O script tem um limite simples de tamanho de mensagem — isso evita gastar
  tokens à toa e é a base do que depois vira rate limiting de verdade quando
  isso virar um endpoint público (webhook da Evolution API).
- A persona tem uma instrução explícita pra ignorar tentativas de mudar seu
  comportamento via mensagem do usuário — uma proteção básica contra prompt
  injection.
- Erros não devem expor detalhes internos (stack trace, chaves, etc.) pro
  usuário final — isso fica mais importante ainda quando virar webhook
  público.

## Próximos passos (depois que esse teste validar)

1. Transformar isso num backend com FastAPI (endpoint `/chat`).
2. Subir no Render.
3. Configurar a Evolution API e apontar o webhook pro endpoint do Render.
4. Plugar o Supabase pra guardar histórico das conversas.
