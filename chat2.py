import hashlib
import json
import logging
import os

import httpx
import streamlit as st
from dotenv import load_dotenv
from oci_openai import OciUserPrincipalAuth
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _log_error(context: str, exc: Exception) -> None:
    logger.error("%s: %s: %s", context, exc.__class__.__name__, exc)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "60"))
COMPARTMENT_ID = _require_env("OCI_COMPARTMENT_ID")
HTTP_CLIENT_HEADERS = {"CompartmentId": COMPARTMENT_ID}
OCI_BASE_URL = _require_env("OCI_BASE_URL")
OCI_CONFIG_FILE = os.path.expanduser(_require_env("OCI_CONFIG_FILE"))
# MODEL_ID = _require_env("OCI_MODEL_ID")
MODEL_ID = "openai.gpt-oss-120b"

DEFAULT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Termo de busca, por exemplo: melhores praias do Brasil",
        }
    },
    "required": ["query"],
    "additionalProperties": False,
}
SEARCH_ERROR_MESSAGE = "Erro ao executar a busca. Tente novamente."
EMPTY_RESPONSE_MESSAGE = "Resposta vazia do servidor. Tente novamente."


@st.cache_resource
def _build_client() -> OpenAI:
    http_client = httpx.Client(
        auth=OciUserPrincipalAuth(config_file=OCI_CONFIG_FILE),
        headers=HTTP_CLIENT_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    return OpenAI(
        api_key="OCI",
        base_url=OCI_BASE_URL,
        http_client=http_client,
    )


client = _build_client()

if "items" not in st.session_state:
    st.session_state["items"] = []
if "pending_tool_calls" not in st.session_state:
    st.session_state.pending_tool_calls = []
if "manual_tool_output_enabled" not in st.session_state:
    st.session_state.manual_tool_output_enabled = False
if "auto_process_pending" not in st.session_state:
    st.session_state.auto_process_pending = False

st.title("💬 Chatbot (Responses)")

st.sidebar.title("Configurações")
st.sidebar.caption("Ajuste o comportamento do assistente.")

st.sidebar.subheader("Sessão")
clear_chat = st.sidebar.button("Limpar conversa")

st.sidebar.subheader("Instruções")
instructions = st.sidebar.text_area(
    "Prompt do sistema",
    value="Você é um assistente útil que pode responder perguntas e ajudar com tarefas.",
)

st.sidebar.subheader("Raciocínio")
reasoning_effort = st.sidebar.radio(
    "Esforço de raciocínio",
    ["baixo", "médio", "alto"],
    index=1,
)

st.sidebar.subheader("Geração")
temperature = st.sidebar.slider(
    "Temperatura", min_value=0.0, max_value=1.0, value=1.0, step=0.01
)
max_output_tokens = st.sidebar.slider(
    "Máx. tokens de saída", min_value=1, max_value=131072, value=30000, step=1000
)

st.sidebar.subheader("Ferramentas")
use_functions = st.sidebar.toggle(
    "Ativar funções",
    value=st.session_state.get("use_functions", False),
    key="use_functions",
)
manual_tool_output = st.session_state.get("manual_tool_output", False)
if use_functions:
    manual_tool_output = st.sidebar.toggle(
        "Saída manual da função",
        value=st.session_state.get("manual_tool_output", False),
        key="manual_tool_output",
    )
else:
    manual_tool_output = False
    st.session_state.manual_tool_output = False
has_pending_tool_calls = bool(st.session_state.pending_tool_calls)
manual_was_enabled = st.session_state.manual_tool_output_enabled
if (manual_was_enabled and not manual_tool_output and has_pending_tool_calls) or (
    not use_functions and has_pending_tool_calls
):
    st.session_state.auto_process_pending = True
st.session_state.manual_tool_output_enabled = manual_tool_output

if clear_chat:
    st.session_state["items"] = []
    st.session_state.pending_tool_calls = []
    st.session_state.auto_process_pending = False
    for key in list(st.session_state.keys()):
        if key.startswith("function_output_"):
            st.session_state.pop(key, None)
    st.rerun()


def _web_search(query: str) -> str:
    payload = {
        "query": query,
        "results": [
            {
                "title": "Fonte de exemplo 1",
                "url": "https://example.com/fonte-1",
                "snippet": f"Resultado simulado para '{query}'.",
            },
            {
                "title": "Fonte de exemplo 2",
                "url": "https://example.com/fonte-2",
                "snippet": f"Outro resultado simulado para '{query}'.",
            },
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _parse_web_search_query(arguments: object) -> str | None:
    if arguments is None:
        return None
    if isinstance(arguments, dict):
        query = arguments.get("query")
        if isinstance(query, str) and query.strip():
            return query.strip()
        return None
    if not isinstance(arguments, str):
        return None
    try:
        args = json.loads(arguments)
    except Exception:
        return None
    if isinstance(args, dict):
        query = args.get("query")
        if isinstance(query, str) and query.strip():
            return query.strip()
    return None


def _web_search_tool():
    return {
        "type": "function",
        "name": "web_search",
        "description": "Buscar informacoes na web",
        "parameters": DEFAULT_TOOL_SCHEMA,
        "strict": True,
    }


def _build_tools():
    if not use_functions:
        return []
    return [_web_search_tool()]


def _prepare_input():
    return st.session_state["items"]


def _call_responses(
    input_items,
    tools,
    *,
    stream: bool,
    instructions_override: str | None = None,
):
    effort_map = {"baixo": "low", "médio": "medium", "alto": "high"}
    params = {
        "model": MODEL_ID,
        "input": input_items,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "stream": stream,
    }
    if tools:
        params["tools"] = tools
    if instructions_override is not None:
        params["instructions"] = instructions_override
    elif instructions.strip():
        params["instructions"] = instructions
    effort_value = effort_map.get(reasoning_effort)
    if effort_value:
        params["reasoning"] = {"effort": effort_value}
    try:
        response = client.responses.create(**params)
    except httpx.TimeoutException as exc:
        _log_error(f"Timeout ao chamar {OCI_BASE_URL}", exc)
        st.error(
            f"Tempo limite excedido ao conectar ao servidor (timeout={REQUEST_TIMEOUT:.0f}s)."
        )
        return None
    except Exception as exc:
        _log_error("Falha ao chamar o serviço", exc)
        st.error(f"Falha ao chamar o serviço: {exc}")
        return None
    logger.info(
        "Responses OK model=%s stream=%s",
        params.get("model"),
        stream,
    )
    return response


def _normalize_output(output_items, content):
    if output_items:
        return output_items
    if content:
        return [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": content}],
            }
        ]
    return []


def _as_dict(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return None


def _coerce_items(items):
    coerced = []
    for item in items or []:
        data = _as_dict(item)
        if data is not None:
            coerced.append(data)
    return coerced


def _extract_tool_calls(output_items):
    return [item for item in output_items if item.get("type") == "function_call"]


def _stream_response(create_container, stream):
    content = ""
    placeholder = None
    output_items = []
    final_response = None
    with st.spinner("Respondendo…"):
        try:
            for event in stream:
                event_type = getattr(event, "type", None)
                if event_type == "response.output_text.delta":
                    delta = getattr(event, "delta", "") or ""
                    if delta:
                        if placeholder is None:
                            placeholder = create_container().empty()
                        content += delta
                        placeholder.markdown(content)
                elif event_type == "response.output_item.done":
                    item = _as_dict(getattr(event, "item", None))
                    if item:
                        output_items.append(item)
                elif event_type == "response.completed":
                    final_response = _as_dict(getattr(event, "response", None))
        except Exception as exc:
            _log_error("Erro no streaming", exc)
            st.error(f"Erro no streaming: {exc}")

    if final_response is not None:
        output_items = (
            _coerce_items(final_response.get("output", output_items)) or output_items
        )
    return {"output": _normalize_output(_coerce_items(output_items), content)}


def _append_assistant_error(message: str) -> None:
    if not message:
        return
    logger.error("Erro exibido ao usuario: %s", message)
    st.error(message)
    st.session_state["items"].append(
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": message}],
        }
    )
    with st.chat_message("assistant"):
        st.markdown(message)


def _handle_tool_calls(tool_calls) -> tuple[bool, str | None]:
    error_message = None
    for call in tool_calls:
        name = call.get("name")
        arguments = call.get("arguments")
        if name == "web_search":
            query = _parse_web_search_query(arguments)
            if not query:
                logger.error("Argumentos inválidos para web_search: %s", arguments)
                error_message = SEARCH_ERROR_MESSAGE
                output = json.dumps({"error": SEARCH_ERROR_MESSAGE}, ensure_ascii=False)
            else:
                try:
                    output = _web_search(query)
                except Exception as exc:
                    _log_error(f"Erro ao executar web_search. query={query}", exc)
                    error_message = SEARCH_ERROR_MESSAGE
                    output = json.dumps(
                        {"error": SEARCH_ERROR_MESSAGE}, ensure_ascii=False
                    )
        else:
            output = json.dumps(
                {"message": "Funcao nao implementada."}, ensure_ascii=False
            )
        call_id = call.get("call_id") or call.get("id")
        if not isinstance(call_id, str) or not call_id:
            logger.error("Tool call sem id: %s", call)
            error_message = SEARCH_ERROR_MESSAGE
            return False, error_message
        st.session_state["items"].append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": output,
            }
        )
    return True, error_message


def _drop_pending_tool_calls(pending_calls):
    call_ids = {
        call.get("call_id") or call.get("id")
        for call in pending_calls
        if isinstance(call.get("call_id") or call.get("id"), str)
    }
    if not call_ids:
        return
    st.session_state["items"] = [
        item
        for item in st.session_state["items"]
        if not (
            item.get("type") == "function_call"
            and (item.get("call_id") in call_ids or item.get("id") in call_ids)
        )
    ]


def _follow_up_instructions():
    follow_instructions = instructions.strip()
    if follow_instructions:
        follow_instructions += "\n\n"
    follow_instructions += (
        "Responda usando a saída da ferramenta enviada. Não chame ferramentas novamente."
    )
    return follow_instructions


def _call_follow_up():
    return _call_responses(
        _prepare_input(),
        [],
        stream=True,
        instructions_override=_follow_up_instructions(),
    )


def run():
    tools = _build_tools()
    response = _call_responses(_prepare_input(), tools, stream=True)
    if response is None:
        return

    first = _stream_response(lambda: st.chat_message("assistant"), response)
    output_items = first.get("output", [])
    tool_calls = _extract_tool_calls(output_items)
    if not output_items and not tool_calls:
        logger.error("Resposta vazia: sem output_items e sem tool_calls.")
        _append_assistant_error(EMPTY_RESPONSE_MESSAGE)
        return
    if output_items:
        st.session_state["items"].extend(output_items)
    if tool_calls:
        if manual_tool_output:
            st.session_state.pending_tool_calls = tool_calls
            st.rerun()
            return
        handled, tool_error = _handle_tool_calls(tool_calls)
        if not handled:
            _drop_pending_tool_calls(tool_calls)
            if tool_error:
                _append_assistant_error(tool_error)
            return
        if tool_error:
            _append_assistant_error(tool_error)
            return
        follow_up = _call_follow_up()
        if follow_up is None:
            return
        final = _stream_response(lambda: st.chat_message("assistant"), follow_up)
        follow_items = final.get("output", [])
        if follow_items:
            st.session_state["items"].extend(follow_items)


def _render_items():
    for item in st.session_state["items"]:
        item_type = item.get("type")
        if item_type == "message":
            role = item.get("role", "assistant")
            content_items = item.get("content") or []
            text_parts = []
            for part in content_items:
                part_type = part.get("type")
                if part_type in ("input_text", "output_text", "text"):
                    text = part.get("text") or ""
                    if text:
                        text_parts.append(text)
            if text_parts:
                with st.chat_message(role):
                    st.markdown("\n".join(text_parts))


def _render_manual_tool_form():
    if not manual_tool_output:
        return
    pending_calls = st.session_state.pending_tool_calls
    if not pending_calls:
        return
    with st.form("function_output_form"):
        st.subheader("Saída da função")
        outputs: dict[str, str] = {}
        for call in pending_calls:
            name = call.get("name") or "função"
            arguments = call.get("arguments") or "{}"
            st.markdown(f"- `{name}`")
            st.code(arguments, language="json")
            call_id = call.get("call_id") or call.get("id")
            if not isinstance(call_id, str) or not call_id:
                logger.error("Tool call sem id no formulário manual: %s", call)
                st.error("Tool call sem id. Não é possível enviar saída.")
                st.stop()
            if name == "web_search":
                query = _parse_web_search_query(arguments)
                if not query:
                    default_output = json.dumps(
                        {"error": SEARCH_ERROR_MESSAGE}, ensure_ascii=False
                    )
                else:
                    try:
                        default_output = _web_search(query)
                    except Exception:
                        default_output = json.dumps(
                            {"error": SEARCH_ERROR_MESSAGE}, ensure_ascii=False
                        )
            else:
                default_output = ""
            output_fingerprint = hashlib.sha1(arguments.encode("utf-8")).hexdigest()[:8]
            output_key = f"function_output_{call_id}_{output_fingerprint}"
            if output_key not in st.session_state:
                st.session_state[output_key] = default_output
            outputs[call_id] = st.text_area(
                f"Informe a saída para `{name}`",
                key=output_key,
                height=140,
            )
        submitted = st.form_submit_button("Enviar saída")
    if not submitted:
        return
    for call in pending_calls:
        call_id = call.get("call_id") or call.get("id")
        output_value = (outputs.get(call_id) or "").strip()
        if not output_value:
            logger.error("Saída da função vazia. tool_call_id=%s", call_id)
            st.error("A saída da função não pode ser vazia.")
            st.stop()
        st.session_state["items"].append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "tool_call_id": call_id,
                "output": output_value,
            }
        )
    st.session_state.pending_tool_calls = []
    follow_up = _call_follow_up()
    if follow_up is None:
        return
    final = _stream_response(lambda: st.chat_message("assistant"), follow_up)
    follow_items = final.get("output", [])
    if follow_items:
        st.session_state["items"].extend(follow_items)
    st.rerun()


def _auto_process_pending_tools():
    if not st.session_state.auto_process_pending:
        return
    pending_calls = st.session_state.pending_tool_calls
    st.session_state.auto_process_pending = False
    if not pending_calls:
        return
    st.toast("Processando ferramentas automaticamente…")
    handled, tool_error = _handle_tool_calls(pending_calls)
    if not handled:
        st.session_state.pending_tool_calls = []
        _drop_pending_tool_calls(pending_calls)
        st.toast("Falha no processamento automático. Pendências descartadas.")
        if tool_error:
            _append_assistant_error(tool_error)
        return
    st.session_state.pending_tool_calls = []
    if tool_error:
        _append_assistant_error(tool_error)
        return
    follow_up = _call_follow_up()
    if follow_up is None:
        return
    final = _stream_response(lambda: st.chat_message("assistant"), follow_up)
    follow_items = final.get("output", [])
    if follow_items:
        st.session_state["items"].extend(follow_items)
    st.rerun()


_render_items()
_render_manual_tool_form()
_auto_process_pending_tools()

input_disabled = manual_tool_output and has_pending_tool_calls
if prompt := st.chat_input("Digite uma mensagem...", disabled=input_disabled):
    st.session_state["items"].append(
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        }
    )
    with st.chat_message("user"):
        st.markdown(prompt)
    run()
