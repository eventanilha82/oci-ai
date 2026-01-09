# oci-ai

Scripts de exemplo para OCI + LangChain/Responses.

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

## LiteLLM (Docker Compose)
Arquivos: `docker-compose.yml`, `config.yaml`, `prometheus.yml`.
O compose sobe o proxy LiteLLM, Postgres e Prometheus (LLMOps).

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

UI do LiteLLM:
- http://localhost:4000/ui

Testar o proxy local:
```
uv run python call_litellm.py
```

O exemplo `call_litellm.py` usa `LITELLM_API_KEY` do `.env` e carrega via `python-dotenv`.

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
```

## Notas
- Apps com `OCI_BASE_URL`: `app_api.py`, `app_context.py`, `app_image.py`, `app_output.py`, `app_reasoning.py`, `app_tool.py`.
- Apps com `OCI_SERVICE_ENDPOINT`: `app_langchain.py`, `app_langchain_react.py`, `app_langchain_output.py`.
- `app_langchain_output.py` faz stream de JSON formatado em tempo real.
