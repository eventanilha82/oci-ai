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
