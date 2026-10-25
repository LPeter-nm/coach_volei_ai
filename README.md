# Teste de stack — Coach Vôlei (motor de IA)

Protótipo usado pra validar, na prática, a stack planejada pro **Contaí**
(Google AI Studio/Gemini, Python, FastAPI, Supabase, Render e Evolution
API) antes de começar o projeto de verdade. A persona de teste é o
**Coach Vôlei**, um assistente que só responde dúvidas sobre voleibol.

## Arquitetura

```
WhatsApp (usuário)
     ↓↑
Evolution API (self-host no Render)
     ↓↑
Backend FastAPI (main.py, no Render)
     ↓↑
Gemini API (Google AI Studio)
     ↓
Supabase (banco da Evolution API)
```

## Estrutura do projeto

- `persona.py` — define quem é a IA (nome, tom, escopo, regras).
- `main.py` — backend FastAPI com três endpoints:
  - `/chat` — pra testes manuais (via `/docs` no navegador).
  - `/webhook` — recebe mensagens da Evolution API e responde no WhatsApp.
  - `/health` — checagem simples de que o serviço está no ar.
- `requirements.txt` — dependências Python do projeto.
- `.env.example` — modelo das variáveis de ambiente necessárias.
- `.gitignore` — mantém `.env` e `venv/` fora do repositório.
- `ativar-venv.bat` — ativa (criando se preciso) o ambiente virtual no Windows.
- `alternar-scripts-powershell.bat` — liga/desliga a permissão de rodar
  scripts `.ps1` no PowerShell do usuário atual (só necessário se o venv
  for ativado por lá em vez do Prompt de Comando).

## Como rodar localmente

1. Ative o ambiente virtual (`ativar-venv.bat` no Windows, ou manualmente
   com `python -m venv venv` + `source venv/bin/activate` no Linux/Mac).
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Copie `.env.example` para `.env` e preencha pelo menos `GEMINI_API_KEY`
   (pegue em https://aistudio.google.com/app/apikey).
4. Pra testar o backend completo (como ele roda em produção):
   ```bash
   uvicorn main:app --reload
   ```
   Depois abra http://127.0.0.1:8000/docs e teste o endpoint `/chat`.

## Variáveis de ambiente

| Variável | Obrigatória | Pra quê serve |
|---|---|---|
| `GEMINI_API_KEY` | Sim | Autentica com a Gemini API |
| `EVOLUTION_API_URL` | Só pro `/webhook` | URL da sua Evolution API |
| `EVOLUTION_INSTANCE` | Só pro `/webhook` | Nome da instância conectada |
| `EVOLUTION_API_KEY` | Só pro `/webhook` | Apikey da instância, pra enviar mensagens |
| `WEBHOOK_SECRET` | Só pro `/webhook` | Token que valida que a chamada veio da Evolution API |
| `ALLOWED_NUMBERS` | Opcional | Lista de números (separados por vírgula) autorizados a falar com o bot; vazio = libera todo mundo |

## Deploy (produção de teste)

1. **Backend (`main.py`)**: Web Service no Render, conectado ao repositório.
   Build Command: `pip install -r requirements.txt`. Start Command:
   `uvicorn main:app --host 0.0.0.0 --port $PORT`. Variáveis de ambiente
   configuradas direto no painel do Render (não no `.env`).
2. **Evolution API**: outro Web Service no Render, a partir da imagem
   Docker `evoapicloud/evolution-api`. Banco de dados: Postgres do Supabase
   (`DATABASE_ENABLED=true`, `DATABASE_PROVIDER=postgresql`,
   `DATABASE_CONNECTION_URI=<connection string do Supabase>`). Cache local
   em vez de Redis (`CACHE_REDIS_ENABLED=false`, `CACHE_LOCAL_ENABLED=true`).
3. Dentro do Manager da Evolution API, criada uma instância conectada a um
   número de WhatsApp dedicado para teste (separado do número pessoal), com
   webhook apontando pro `/webhook` do backend, evento `MESSAGES_UPSERT`.

## Notas de segurança

- Nenhuma chave fica no código — tudo via variável de ambiente (`.env`
  local, ou configurado direto no painel do Render em produção).
- O webhook valida um token secreto (`WEBHOOK_SECRET`) no cabeçalho
  `Authorization` antes de processar qualquer requisição.
- Limite de tamanho de mensagem, pra evitar gasto desnecessário de tokens.
- A persona tem instrução explícita pra ignorar tentativas de mudar seu
  comportamento via mensagem do usuário (proteção básica contra prompt
  injection).
- Erros não expõem detalhes internos (stack trace, chaves etc.) pro
  usuário final.
- Filtro opcional de números autorizados (`ALLOWED_NUMBERS`), pra usar
  mesmo num número de teste sem responder a qualquer estranho.
- O teste usa um número de WhatsApp dedicado, separado do pessoal.

## Limitações conhecidas (é um teste, não o Contaí final)

- O histórico de conversa (`conversas_por_numero` em `main.py`) vive em
  memória — some se o backend reiniciar. No Contaí de verdade, isso
  precisa ser persistido (ex: no próprio Supabase).
- Plano gratuito do Render "dorme" após inatividade; a primeira mensagem
  depois disso demora mais pra responder.

## Próximos passos

- Persistir o histórico de conversas no Supabase.
- Repetir esse mesmo roteiro, já com o tema e a persona reais do Contaí.

## Licença

Este repositório está sob a licença MIT — veja o arquivo [LICENSE](./LICENSE).
