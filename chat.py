import hashlib
import json
import logging
import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)
logging.getLogger("urllib3").setLevel(logging.WARNING)


def _log_error(context: str, exc: Exception) -> None:
    logger.error("%s: %s: %s", context, exc.__class__.__name__, exc)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


MODEL_ID = "openai-gpt-oss-120b"
URL = "http://localhost:4000/v1/chat/completions"
API_KEY = _require_env("LITELLM_API_KEY")

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

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_tool_calls" not in st.session_state:
    st.session_state.pending_tool_calls = []
if "manual_tool_output_enabled" not in st.session_state:
    st.session_state.manual_tool_output_enabled = False
if "auto_process_pending" not in st.session_state:
    st.session_state.auto_process_pending = False

st.title("💬 Chatbot (Chat Completions)")

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
    st.session_state.messages = []
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
        "function": {
            "name": "web_search",
            "description": "Buscar informacoes na web",
            "parameters": DEFAULT_TOOL_SCHEMA,
            "strict": True,
        },
    }


def _build_tools():
    if not use_functions:
        return []
    return [_web_search_tool()]


def _build_tools_for_pending(pending_calls):
    tool_names = {
        call.get("function", {}).get("name") or call.get("name")
        for call in pending_calls
    }
    tools = []
    if "web_search" in tool_names:
        tools.append(_web_search_tool())
    return tools


def _resolve_tools_for_pending(pending_calls):
    tools = _build_tools()
    if tools:
        return tools
    return _build_tools_for_pending(pending_calls)


def _prepare_messages():
    if not instructions.strip():
        return st.session_state.messages
    return [{"role": "system", "content": instructions}] + st.session_state.messages


def _call_chat(
    messages, tools, *, stream: bool, tool_choice: str | dict | None = None
):
    effort_map = {"baixo": "low", "médio": "medium", "alto": "high"}
    payload = {
        "model": MODEL_ID,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
        "stream": stream,
    }
    if tools:
        payload["tools"] = tools
    effort_value = effort_map.get(reasoning_effort)
    if effort_value:
        payload["reasoning"] = {"effort": effort_value}
    if tool_choice:
        payload["tool_choice"] = tool_choice
    try:
        response = requests.post(
            URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            stream=stream,
            timeout=60,
        )
    except requests.Timeout as exc:
        _log_error(f"Timeout ao chamar {URL}", exc)
        st.error("Tempo limite excedido ao conectar ao servidor (timeout=60s).")
        return None
    except requests.RequestException as exc:
        _log_error("Falha ao conectar ao servidor", exc)
        st.error(f"Falha ao conectar ao servidor: {exc}")
        return None
    if response.status_code >= 400:
        logger.error("HTTP %s: %s", response.status_code, response.text)
        st.error(f"HTTP {response.status_code}: {response.text}")
        return None
    logger.info(
        "Chat completions OK status=%s stream=%s",
        response.status_code,
        stream,
    )
    return response


def _stream_chat_response(create_container, response):
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        st.warning("Servidor não retornou streaming; exibindo resposta completa.")
        try:
            data = response.json()
        except Exception as exc:
            _log_error("Resposta inválida do servidor (sem stream)", exc)
            logger.error("Body: %s", response.text)
            st.error("Resposta inválida do servidor.")
            return {"content": "", "tool_calls": []}
        message = data.get("choices", [{}])[0].get("message", {})
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []
        if content:
            create_container().markdown(content)
        return {"content": content, "tool_calls": tool_calls}

    content = ""
    placeholder = None
    tool_calls: dict[object, dict] = {}
    ordered_keys: list[object] = []
    auto_index = 0
    with st.spinner("Respondendo…"):
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data_str = line[len("data:") :].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
            except Exception:
                continue
            delta = data.get("choices", [{}])[0].get("delta", {})
            piece = delta.get("content")
            if piece:
                if placeholder is None:
                    placeholder = create_container().empty()
                content += piece
                placeholder.markdown(content)
            for call in delta.get("tool_calls", []) or []:
                idx = call.get("index")
                key = None
                if isinstance(idx, int):
                    key = idx
                elif isinstance(idx, str) and idx.isdigit():
                    key = int(idx)
                if key is None:
                    key = call.get("id")
                if key is None:
                    key = f"auto_{auto_index}"
                    auto_index += 1
                if key not in tool_calls:
                    ordered_keys.append(key)
                entry = tool_calls.setdefault(
                    key,
                    {
                        "id": None,
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                if call.get("id"):
                    entry["id"] = call["id"]
                if call.get("type"):
                    entry["type"] = call["type"]
                func = call.get("function") or {}
                if func.get("name"):
                    entry["function"]["name"] = func["name"]
                if func.get("arguments"):
                    entry["function"]["arguments"] += func["arguments"]
    calls = [tool_calls[key] for key in ordered_keys]
    return {"content": content, "tool_calls": calls}


def _append_assistant_error(message: str) -> None:
    if not message:
        return
    logger.error("Erro exibido ao usuario: %s", message)
    st.error(message)
    st.session_state.messages.append({"role": "assistant", "content": message})
    with st.chat_message("assistant"):
        st.markdown(message)


def _handle_tools(tool_calls) -> tuple[bool, str | None]:
    error_message = None
    for call in tool_calls:
        if call.get("type") != "function":
            continue
        function = call.get("function", {})
        name = function.get("name")
        arguments = function.get("arguments")
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
                    output = json.dumps({"error": SEARCH_ERROR_MESSAGE}, ensure_ascii=False)
        else:
            output = json.dumps(
                {"message": "Funcao nao implementada."}, ensure_ascii=False
            )
        tool_call_id = call.get("id")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            logger.error("Tool call sem id: %s", call)
            error_message = SEARCH_ERROR_MESSAGE
            return False, error_message
        st.session_state.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": output,
            }
        )
    return True, error_message


def _drop_pending_tool_calls(pending_calls):
    call_ids = {
        call.get("id") or call.get("call_id")
        for call in pending_calls
        if isinstance(call.get("id") or call.get("call_id"), str)
    }
    if not call_ids:
        return
    st.session_state.messages = [
        item
        for item in st.session_state.messages
        if not (
            item.get("role") == "assistant"
            and item.get("tool_calls")
            and any(
                (call.get("id") in call_ids or call.get("call_id") in call_ids)
                for call in item.get("tool_calls", [])
            )
        )
    ]


def run():
    tools = _build_tools()
    response = _call_chat(_prepare_messages(), tools, stream=True)
    if response is None:
        return

    first = _stream_chat_response(lambda: st.chat_message("assistant"), response)
    tool_calls = first.get("tool_calls") or []
    if tool_calls:
        assistant_msg = {"role": "assistant", "tool_calls": tool_calls}
        if first.get("content"):
            assistant_msg["content"] = first["content"]
        st.session_state.messages.append(assistant_msg)
        if manual_tool_output:
            st.session_state.pending_tool_calls = tool_calls
            st.rerun()
            return
        handled, tool_error = _handle_tools(tool_calls)
        if not handled:
            _drop_pending_tool_calls(tool_calls)
            if tool_error:
                _append_assistant_error(tool_error)
            return
        if tool_error:
            _append_assistant_error(tool_error)
            return
        follow_up = _call_chat(
            _prepare_messages(), tools, stream=True, tool_choice="none"
        )
        if follow_up is None:
            return
        final = _stream_chat_response(lambda: st.chat_message("assistant"), follow_up)
        if final.get("content"):
            st.session_state.messages.append(
                {"role": "assistant", "content": final["content"]}
            )
    else:
        if first.get("content"):
            st.session_state.messages.append(
                {"role": "assistant", "content": first["content"]}
            )
        else:
            logger.error("Resposta vazia: sem content e sem tool_calls.")
            _append_assistant_error(EMPTY_RESPONSE_MESSAGE)


def _render_messages():
    for msg in st.session_state.messages:
        role = msg.get("role")
        content = msg.get("content")
        if role == "user" and isinstance(content, str) and content.strip():
            with st.chat_message("user"):
                st.markdown(content)
        elif role == "assistant" and isinstance(content, str) and content.strip():
            with st.chat_message("assistant"):
                st.markdown(content)


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
            name = call.get("function", {}).get("name") or call.get("name") or "função"
            arguments = (
                call.get("function", {}).get("arguments")
                or call.get("arguments")
                or "{}"
            )
            st.markdown(f"- `{name}`")
            st.code(arguments, language="json")
            call_id = call.get("id") or call.get("call_id")
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
        tool_call_id = call.get("id") or call.get("call_id")
        output_value = (outputs.get(tool_call_id) or "").strip()
        if not output_value:
            logger.error("Saída da função vazia. tool_call_id=%s", tool_call_id)
            st.error("A saída da função não pode ser vazia.")
            st.stop()
        st.session_state.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": output_value,
            }
        )
    st.session_state.pending_tool_calls = []
    follow_up = _call_chat(
        _prepare_messages(),
        _resolve_tools_for_pending(pending_calls),
        stream=True,
        tool_choice="none",
    )
    if follow_up is None:
        return
    final = _stream_chat_response(lambda: st.chat_message("assistant"), follow_up)
    if final.get("content"):
        st.session_state.messages.append(
            {"role": "assistant", "content": final["content"]}
        )
    st.rerun()


def _auto_process_pending_tools():
    if not st.session_state.auto_process_pending:
        return
    pending_calls = st.session_state.pending_tool_calls
    st.session_state.auto_process_pending = False
    if not pending_calls:
        return
    st.toast("Processando ferramentas automaticamente…")
    handled, tool_error = _handle_tools(pending_calls)
    if not handled:
        st.session_state.pending_tool_calls = []
        st.toast("Falha no processamento automático. Pendências descartadas.")
        if tool_error:
            _append_assistant_error(tool_error)
        return
    st.session_state.pending_tool_calls = []
    if tool_error:
        _append_assistant_error(tool_error)
        return
    follow_up = _call_chat(
        _prepare_messages(),
        _resolve_tools_for_pending(pending_calls),
        stream=True,
        tool_choice="none",
    )
    if follow_up is None:
        return
    final = _stream_chat_response(lambda: st.chat_message("assistant"), follow_up)
    if final.get("content"):
        st.session_state.messages.append(
            {"role": "assistant", "content": final["content"]}
        )
    st.rerun()


_render_messages()
_render_manual_tool_form()
_auto_process_pending_tools()

input_disabled = manual_tool_output and has_pending_tool_calls
if prompt := st.chat_input("Digite uma mensagem...", disabled=input_disabled):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    run()
