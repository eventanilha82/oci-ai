# oci-ai

Scripts e exemplos para OCI GenAI, LangChain, LiteLLM e OpenWebUI.

## Requisitos
- Python 3.14+
- uv (https://docs.astral.sh/uv/)

## Instalacao do uv
Opcao 1 (Homebrew):
```
brew install uv
```

Opcao 2 (script oficial):
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Opcao 3 (Windows PowerShell):
```
irm https://astral.sh/uv/install.ps1 | iex
```

Opcao 4 (Windows com WSL):
Use os mesmos comandos de Linux dentro do WSL (Opcao 2).

## Configuracao
1) Copie o template:
```
cp .env.template .env
```
2) Preencha as variaveis no `.env`.

## Setup OCI (API Auth)
Siga o guia oficial de autenticação OCI: https://docs.oracle.com/pt-br/iaas/Content/generative-ai-agents/setup-oci-api-auth.htm

Resumo do que precisa estar pronto:
- Tenha uma tenancy OCI ativa e um usuário com permissões para Generative AI.
- Gere ou configure credenciais de API (chave pública/privada) e associe ao usuário.
- Crie/edite o arquivo de configuração OCI (ex.: `~/.oci/config`) com `user`, `tenancy`, `fingerprint`, `key_file`, `region`.
- Use o caminho desse arquivo em `OCI_CONFIG_FILE` no `.env`.
- Garanta o `OCI_COMPARTMENT_ID`, `OCI_SERVICE_ENDPOINT` e `OCI_MODEL_ID` corretos.

## LiteLLM + OpenWebUI (Docker Compose)
Arquivos: `docker-compose.yml`, `config.yaml`.
O compose sobe:
- LiteLLM (proxy OpenAI-compat)
- Postgres (persistencia do LiteLLM)
- Prometheus (metrics)
- OpenWebUI (UI)

Os dados ficam em `data/` (Postgres, Prometheus e OpenWebUI). A pasta esta no `.gitignore`.

Variáveis adicionais no `.env`:
- `LITELLM_MASTER_KEY`
- `LITELLM_SALT_KEY`
- `LITELLM_API_KEY`
- `OCI_REGION`
- `OCI_USER`
- `OCI_FINGERPRINT`
- `OCI_TENANCY`
- `OCI_KEY`

Subir o proxy:
```
docker compose up -d
```

Parar o compose:
```
docker compose down
```

UIs:
- LiteLLM: http://localhost:4000/ui
- OpenWebUI: http://localhost:3000
- Prometheus: http://localhost:9090

Endpoints:
- OpenAI-compat proxy: `http://localhost:4000`
- Metrics LiteLLM: `http://localhost:4000/metrics/` (tem redirect de `/metrics` -> `/metrics/`)

Testar o proxy local:
```
uv run python call_litellm.py
```

`call_litellm.py` usa `LITELLM_API_KEY`, chama o proxy `http://localhost:4000` com `gemini-2-5-flash-lite` (config.yaml) e imprime resposta + usage.

Modelos (LiteLLM):
- Veja `config.yaml` para os modelos OCI cadastrados.
- Todos usam a mesma credencial OCI em `credential_list`.

OpenWebUI:
- O compose ja aponta `OPENAI_API_BASE_URL` para `http://litellm:4000`.
- Use `LITELLM_API_KEY` para autenticar.

## Como rodar
Cada app pode ser executado com `uv run`:

```
uv run app_api.py
uv run app_context.py
uv run app_image.py
uv run app_langchain.py
uv run app_langchain_react.py
uv run app_langchain_output.py
uv run app_output.py
uv run app_reasoning.py
uv run app_tool.py
uv run call_classif.py
uv run call_litellm.py
```

## Notas
- Apps com `OCI_BASE_URL`: `app_api.py`, `app_context.py`, `app_image.py`, `app_output.py`, `app_reasoning.py`, `app_tool.py`.
- Apps com `OCI_SERVICE_ENDPOINT`: `app_langchain.py`, `app_langchain_react.py`, `app_langchain_output.py`.
- `app_langchain_output.py` faz stream de JSON formatado em tempo real.
- `call_classif.py` faz classificacao com schema Pydantic via LiteLLM.
