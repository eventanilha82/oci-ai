# oci-ai

Scripts e exemplos para OCI GenAI, LangChain, LiteLLM e OpenWebUI.

## Requisitos
- Python 3.12+
- uv (https://docs.astral.sh/uv/)

## Instalação do uv
Opção 1 (Homebrew):
```
brew install uv
```

Opção 2 (script oficial):
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Opção 3 (Windows PowerShell):
```
irm https://astral.sh/uv/install.ps1 | iex
```

Opção 4 (Windows com WSL):
Use os mesmos comandos de Linux dentro do WSL (Opção 2).

## Configuração
1) Copie o template:
```
cp .env.template .env
```
2) Preencha as variáveis no `.env`.

Exemplo mínimo de `.env` (ajuste para sua tenancy):
```
OCI_CONFIG_FILE=/home/opc/.oci/config
OCI_COMPARTMENT_ID=ocid1.compartment.oc1...
OCI_CONVERSATION_STORE_ID=ocid1.generativeaiconversationstore.oc1...
OCI_SERVICE_ENDPOINT=https://generativeai.us-chicago-1.oci.oraclecloud.com
OCI_MODEL_ID=ocid1.generativeaimodel.oc1...
LITELLM_MASTER_KEY=troque-por-um-segredo
LITELLM_SALT_KEY=troque-por-um-segredo
LITELLM_API_KEY=troque-por-um-segredo
OCI_REGION=us-chicago-1
OCI_USER=ocid1.user.oc1...
OCI_FINGERPRINT=aa:bb:cc:dd:ee:ff:...
OCI_TENANCY=ocid1.tenancy.oc1...
OCI_KEY="-----BEGIN PRIVATE KEY-----\n...conteúdo...\n-----END PRIVATE KEY-----"
```

Variáveis essenciais:
- OCI: `OCI_CONFIG_FILE`, `OCI_COMPARTMENT_ID`, `OCI_CONVERSATION_STORE_ID`, `OCI_SERVICE_ENDPOINT`, `OCI_MODEL_ID`
- LiteLLM: `LITELLM_MASTER_KEY`, `LITELLM_SALT_KEY`, `LITELLM_API_KEY`

## Guia rápido: VM (OCI) + Docker + Deploy
1) Acesso via SSH:
```
ssh -i ssh.key opc@IP_DA_VM
```

Opcional (VS Code Remote - SSH):
- Instale a extensão "Remote - SSH".
- Adicione a VM ao `~/.ssh/config`:
```
Host oci-ai
  HostName IP_DA_VM
  User opc
  IdentityFile ~/.ssh/ssh.key
```
- Conecte com `ssh oci-ai` ou via "Remote Explorer".

2) Instalar Docker e Git (Oracle Linux):
```
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager -y --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker opc
sudo dnf install -y git
```
Saia e entre novamente para aplicar o grupo `docker`. Verifique com:
```
docker --version
docker compose version
```

3) Baixar o projeto:
```
git clone https://github.com/eventanilha82/oci-ai.git
cd oci-ai
```

4) Configurar `.env` na VM:
```
scp -i ssh.key .env opc@IP_DA_VM:/home/opc/oci-ai/.env
```
Ou edite direto:
```
nano /home/opc/oci-ai/.env
```

5) Configurar OCI e chave privada:
- Crie `~/.oci/config` e aponte `OCI_CONFIG_FILE` no `.env`.
- Chave privada do LiteLLM precisa estar em uma linha no `.env`:
```
OCI_KEY="-----BEGIN PRIVATE KEY-----\n...conteúdo...\n-----END PRIVATE KEY-----"
```
Exemplo mínimo de `~/.oci/config`:
```
[DEFAULT]
user=ocid1.user.oc1...
tenancy=ocid1.tenancy.oc1...
fingerprint=aa:bb:cc:dd:ee:ff:...
key_file=/home/opc/.oci/oci_api_key.pem
region=us-chicago-1
```
Se quiser usar uma LLM para formatar sua chave:
```
Formate minha chave SSH como uma única linha para .env no formato OCI_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
```

6) Liberar portas no firewall da VM:
```
sudo dnf install -y firewalld
sudo systemctl enable --now firewalld
sudo firewall-cmd --permanent --add-port=22/tcp
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --permanent --add-port=3000/tcp
sudo firewall-cmd --permanent --add-port=4000/tcp
sudo firewall-cmd --reload
```
Portas usadas:
- 22 (SSH)
- 80 (se estiver publicando algo via HTTP)
- 3000 (OpenWebUI)
- 4000 (LiteLLM)
- 9090 (Prometheus, opcional)
Também libere essas portas nas regras de rede da OCI (VCN/NSG/Security List).

7) Subir o compose e acessar:
```
docker compose up -d
```
- OpenWebUI: `http://IP_PUBLICO:3000`
- LiteLLM: `http://IP_PUBLICO:4000/ui`
- Prometheus: `http://IP_PUBLICO:9090` (se exposto)
No primeiro acesso do OpenWebUI, crie o usuário admin.

## Setup OCI (API Auth)
Siga o guia oficial de autenticação OCI: https://docs.oracle.com/pt-br/iaas/Content/generative-ai-agents/setup-oci-api-auth.htm

Resumo do que precisa estar pronto:
- Tenha uma tenancy OCI ativa e um usuário com permissões para Generative AI.
- Gere ou configure credenciais de API (chave pública/privada) e associe ao usuário.
- Crie/edite o arquivo de configuração OCI (ex.: `~/.oci/config`) com `user`, `tenancy`, `fingerprint`, `key_file`, `region`.
- Use o caminho desse arquivo em `OCI_CONFIG_FILE` no `.env`.
- Garanta o `OCI_COMPARTMENT_ID`, `OCI_SERVICE_ENDPOINT` e `OCI_MODEL_ID` corretos.

## Conversation Store (OCI)
Para persistir conversas, crie um Conversation Store no console OCI e use o OCID no `.env`.

Passo a passo (Console OCI):
1) Acesse **Generative AI**.
2) Vá em **Conversation Stores** (ou **Conversations**, conforme sua região).
3) Clique em **Create** e selecione o **compartment** correto.
4) Copie o **OCID** do Conversation Store criado.
5) Preencha `OCI_CONVERSATION_STORE_ID` no `.env`.

Os scripts `app_conversation.py`, `app_conversation2.py` e `app_pdf.py` enviam o header
`opc-conversation-store-id` usando essa variável.

## LiteLLM + OpenWebUI (Docker Compose)
Arquivos: `docker-compose.yml`, `config.yaml`.
O compose sobe:
- LiteLLM (proxy OpenAI-compat)
- Postgres (persistência do LiteLLM)
- Prometheus (metrics)
- OpenWebUI (UI)

Os dados ficam em `data/` (Postgres, Prometheus e OpenWebUI). A pasta está no `.gitignore`.

Variáveis adicionais no `.env`:
- `LITELLM_MASTER_KEY`
- `LITELLM_SALT_KEY`
- `LITELLM_API_KEY`
- `OCI_REGION`
- `OCI_USER`
- `OCI_FINGERPRINT`
- `OCI_TENANCY`
- `OCI_KEY`
- `OPENAI_API_BASE_URL` (apenas se quiser sobrescrever)

UIs:
- LiteLLM: http://localhost:4000/ui
- OpenWebUI: http://localhost:3000
- Prometheus: http://localhost:9090

Endpoints:
- OpenAI-compat proxy: `http://localhost:4000`
- Metrics LiteLLM: `http://localhost:4000/metrics/` (tem redirect de `/metrics` -> `/metrics/`)

Exemplos de uso (local):
```
uv run python call_litellm.py
```

`call_litellm.py` usa `LITELLM_API_KEY`, chama o proxy `http://localhost:4000` com `gemini-2-5-flash-lite` (config.yaml) e imprime resposta + usage.

Teste rápido com curl:
```
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-2-5-flash-lite","messages":[{"role":"user","content":"ping"}]}'
```

Modelos (LiteLLM):
- Veja `config.yaml` para os modelos OCI cadastrados.
- Todos usam a mesma credencial OCI em `credential_list`.

OpenWebUI:
- O compose já aponta `OPENAI_API_BASE_URL` para `http://litellm:4000`.
- Use `LITELLM_API_KEY` para autenticar.

Segurança:
- Evite expor `5432` publicamente.
- Troque os valores default de `LITELLM_MASTER_KEY`/`LITELLM_SALT_KEY`.

## Como rodar
Instale dependências do projeto:
```
uv sync
```

Cada app pode ser executado com `uv run`:

```
uv run app_api.py
uv run app_conversation.py
uv run app_conversation2.py
uv run app_context.py
uv run app_image.py
uv run app_langchain.py
uv run app_langchain_react.py
uv run app_langchain_output.py
uv run app_output.py
uv run app_pdf.py
uv run app_reasoning.py
uv run app_tool.py
uv run chat.py
uv run chat2.py
uv run call_classif.py
uv run call_litellm.py
```

## Streamlit Chat (chat.py / chat2.py)
Dois chats em Streamlit:
- `chat.py`: usa **Chat Completions** via proxy LiteLLM (porta `4000`).
- `chat2.py`: usa **Responses API** direto na OCI.

Como rodar:
```
uv run streamlit run chat.py
uv run streamlit run chat2.py
```

Requisitos:
- `chat.py` precisa de `LITELLM_API_KEY` e do proxy LiteLLM rodando (`http://localhost:4000`).
- `chat2.py` usa `OCI_CONFIG_FILE`, `OCI_COMPARTMENT_ID`, `OCI_CONVERSATION_STORE_ID` e `OCI_MODEL_ID`.

Comandos úteis:
```
docker compose ps
docker compose logs -f litellm
docker compose logs -f openwebui
docker compose down
```

Atualizar o projeto na VM:
```
git pull
docker compose up -d
```

## Notas
- Apps com `OCI_BASE_URL`: `app_api.py`, `app_context.py`, `app_image.py`, `app_output.py`, `app_reasoning.py`, `app_tool.py`.
- Apps com `OCI_SERVICE_ENDPOINT`: `app_langchain.py`, `app_langchain_react.py`, `app_langchain_output.py`.
- `app_langchain_output.py` faz stream de JSON formatado em tempo real.
- `call_classif.py` faz classificação com schema Pydantic via LiteLLM.

## Troubleshooting rápido
Porta fechada:
- Verifique `firewalld` e as regras de rede na OCI (VCN/NSG/Security List).
- Confirme se a porta 22 está liberada para SSH.

Permissão Docker:
- Confirme que fez logout/login depois de `usermod -aG docker opc`.

OCI auth falhando:
- Revise `~/.oci/config`, `OCI_CONFIG_FILE` e se a chave privada está correta (uma linha no `OCI_KEY`).

OpenWebUI não conecta ao LiteLLM:
- Confirme `LITELLM_API_KEY` no `.env` e se o `litellm` está healthy.
- Veja logs com `docker compose logs -f litellm`.

## FAQ rápido
Qual endpoint usar em `OCI_SERVICE_ENDPOINT`?
- Use o endpoint de Generative AI da sua região, ex: `https://generativeai.us-chicago-1.oci.oraclecloud.com`.

Como achar o `OCI_MODEL_ID`?
- No console OCI, vá em Generative AI, selecione o modelo e copie o OCID.

Qual região colocar em `OCI_REGION`?
- A mesma região onde o recurso/modelo foi criado.

## Referências
- LiteLLM (docs): guia oficial de configuração, modelos e proxy OpenAI-compat. https://docs.litellm.ai/docs/
- OCI OpenAI (samples): exemplos oficiais de uso do SDK `oci-openai` em projetos. https://github.com/oracle-samples/oci-openai
- LangChain Oracle: integrações e exemplos do LangChain para OCI. https://github.com/oracle/langchain-oracle/tree/main
- OpenWebUI (docs): configuração da UI, autenticação e integrações com proxies. https://docs.openwebui.com/
