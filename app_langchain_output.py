import json
import os
import time
import warnings

warnings.filterwarnings(
    "ignore",
    message=(
        "Core Pydantic V1 functionality isn't compatible with Python 3.14 or "
        "greater\\."
    ),
)

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_oci import ChatOCIOpenAI
from oci_openai import OciUserPrincipalAuth
from pydantic import BaseModel, Field

load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


def _to_serializable(value: object) -> object:
    if hasattr(value, "model_dump"):
        return _to_serializable(value.model_dump())
    if isinstance(value, dict):
        return {key: _to_serializable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_serializable(item) for item in value]
    return value


def _print_pretty_json(payload: object) -> None:
    try:
        if isinstance(payload, str):
            stripped = payload.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    payload = json.loads(stripped)
                except Exception:
                    pass
        print(json.dumps(_to_serializable(payload), indent=2, ensure_ascii=False))
    except Exception:
        print(repr(payload))


def _print_usage(payload: object) -> None:
    usage = None
    data = None
    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
    elif isinstance(payload, dict):
        data = payload
    if isinstance(data, dict):
        usage = data.get("usage_metadata") or data.get("usage")
        if usage is None:
            messages = data.get("messages")
            if isinstance(messages, list):
                for item in reversed(messages):
                    if isinstance(item, dict):
                        usage = item.get("usage_metadata") or item.get("usage")
                    else:
                        usage = getattr(item, "usage_metadata", None) or getattr(
                            item, "usage", None
                        )
                        if usage is None and hasattr(item, "model_dump"):
                            item_data = item.model_dump()
                            if isinstance(item_data, dict):
                                usage = item_data.get(
                                    "usage_metadata"
                                ) or item_data.get("usage")
                    if usage:
                        break
    if usage is None:
        usage = getattr(payload, "usage_metadata", None) or getattr(
            payload, "usage", None
        )
    if usage:
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()
        if isinstance(usage, dict):
            prompt = usage.get("input_tokens") or usage.get("prompt_tokens")
            completion = usage.get("output_tokens") or usage.get("completion_tokens")
            total = usage.get("total_tokens") or (
                (prompt or 0) + (completion or 0) if prompt or completion else None
            )
            print("\n📊 Uso (tokens):")
            if prompt is not None:
                print(f"- prompt: {prompt}")
            if completion is not None:
                print(f"- saída: {completion}")
            if total is not None:
                print(f"- total: {total}")
        else:
            print(f"\n📊 Uso:\n- {usage}")


class _JsonStreamFormatter:
    def __init__(self) -> None:
        self._indent = 0
        self._in_string = False
        self._escape = False

    def feed(self, text: str) -> str:
        output = []
        for ch in text:
            if self._in_string:
                output.append(ch)
                if self._escape:
                    self._escape = False
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._in_string = False
                continue
            if ch in " \n\r\t":
                continue
            if ch == '"':
                self._in_string = True
                output.append(ch)
                continue
            if ch in "{[":
                output.append(ch)
                self._indent += 1
                output.append("\n" + "  " * self._indent)
                continue
            if ch in "}]":
                self._indent = max(0, self._indent - 1)
                output.append("\n" + "  " * self._indent + ch)
                continue
            if ch == ",":
                output.append(ch)
                output.append("\n" + "  " * self._indent)
                continue
            if ch == ":":
                output.append(": ")
                continue
            output.append(ch)
        return "".join(output)


def _extract_chunk_text(chunk: object) -> str:
    if isinstance(chunk, tuple) and len(chunk) == 2:
        left, right = chunk
        text = _extract_chunk_text(left)
        if text:
            return text
        return _extract_chunk_text(right)
    if isinstance(chunk, list) and chunk:
        parts = []
        for item in chunk:
            text = _extract_chunk_text(item)
            if text:
                parts.append(text)
        return "".join(parts)
    if isinstance(chunk, dict) and "messages" in chunk:
        parts = []
        messages = chunk.get("messages") or []
        if isinstance(messages, list):
            for message in messages:
                text = _extract_chunk_text(message)
                if text:
                    parts.append(text)
        return "".join(parts)
    if isinstance(chunk, dict):
        content = chunk.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if (
                    isinstance(part, dict)
                    and part.get("type") == "text"
                    and part.get("text")
                ):
                    parts.append(part["text"])
            return "".join(parts)
    content = getattr(chunk, "content", None)
    if isinstance(content, list):
        parts = []
        for part in content:
            if (
                isinstance(part, dict)
                and part.get("type") == "text"
                and part.get("text")
            ):
                parts.append(part["text"])
        return "".join(parts)
    return ""


COMPARTMENT_ID = _require_env("OCI_COMPARTMENT_ID")
OCI_SERVICE_ENDPOINT = _require_env("OCI_SERVICE_ENDPOINT")
OCI_CONFIG_FILE = os.path.expanduser(_require_env("OCI_CONFIG_FILE"))
MODEL_ID = _require_env("OCI_MODEL_ID")


def _build_client() -> ChatOCIOpenAI:
    return ChatOCIOpenAI(
        auth=OciUserPrincipalAuth(config_file=OCI_CONFIG_FILE),
        service_endpoint=OCI_SERVICE_ENDPOINT,
        compartment_id=COMPARTMENT_ID,
        model=MODEL_ID,
        store=False,
    )


def _close_client(client: ChatOCIOpenAI) -> None:
    if hasattr(client, "close"):
        client.close()


class ContactInfo(BaseModel):
    """Informações de contato de uma pessoa."""

    name: str = Field(description="O nome da pessoa")
    email: str = Field(description="O endereço de email da pessoa")
    phone: str = Field(description="O número de telefone da pessoa")


class ContactList(BaseModel):
    """Lista de contatos extraidos."""

    contacts: list[ContactInfo] = Field(description="Lista de contatos extraidos")


CONTACTS = [
    "João Silva, joao.silva@example.com, (11) 91234-5678",
    "Maria Souza, maria.souza@example.com, (21) 99876-5432",
    "Carlos Pereira, carlos.pereira@example.com, (31) 95555-1234",
    "Ana Costa, ana.costa@example.com, (41) 93456-7890",
    "Fernanda Lima, fernanda.lima@example.com, (51) 98765-4321",
]

SYSTEM_PROMPT = "Extraia as informações de contato."

PRINT_RAW = False

client = _build_client()

graph = create_agent(
    model=client, response_format=ContactList, system_prompt=SYSTEM_PROMPT
)


def run_with_responses_api() -> None:
    start_time = time.time()
    try:
        contacts_text = "\n".join(CONTACTS)
        messages = [
            HumanMessage(
                content=(
                    "Extraia as informações de contato da lista abaixo e "
                    "retorne todos os itens:\n"
                    f"{contacts_text}"
                )
            ),
        ]
        response = graph.invoke({"messages": messages})
        if PRINT_RAW:
            _print_pretty_json(response)
        else:
            text = _extract_chunk_text(response)
            if text:
                _print_pretty_json(text)
        _print_usage(response)
    except Exception as exc:
        print(f"\n[ERRO Responses create]: {exc}")
    finally:
        elapsed = time.time() - start_time
        print(f"\n⏱️ Tempo (chat.completions create): {elapsed:.2f}s")


def stream_with_responses_api() -> None:
    start_time = time.time()
    try:
        contacts_text = "\n".join(CONTACTS)
        messages = [
            HumanMessage(
                content=(
                    "Extraia as informações de contato da lista abaixo e "
                    "retorne todos os itens:\n"
                    f"{contacts_text}"
                )
            ),
        ]
        last_usage = None
        if PRINT_RAW:
            for chunk in graph.stream({"messages": messages}, stream_mode="messages"):
                _print_pretty_json(chunk)
                last_usage = chunk
        else:
            formatter = _JsonStreamFormatter()
            for chunk in graph.stream({"messages": messages}, stream_mode="messages"):
                text = _extract_chunk_text(chunk)
                if text:
                    formatted = formatter.feed(text)
                    if formatted:
                        print(formatted, end="", flush=True)
                if getattr(chunk, "usage_metadata", None) or getattr(
                    chunk, "usage", None
                ):
                    last_usage = chunk
                elif isinstance(chunk, dict) and (
                    "usage_metadata" in chunk or "usage" in chunk
                ):
                    last_usage = chunk
                elif isinstance(chunk, (list, tuple)):
                    for item in chunk:
                        if getattr(item, "usage_metadata", None) or getattr(
                            item, "usage", None
                        ):
                            last_usage = item
                            break
                        if isinstance(item, dict) and (
                            "usage_metadata" in item or "usage" in item
                        ):
                            last_usage = item
                            break
        if not PRINT_RAW:
            print()
        if PRINT_RAW and last_usage is not None:
            _print_usage(last_usage)
    except Exception as exc:
        print(f"\n[ERRO Responses stream]: {exc}")
    finally:
        elapsed = time.time() - start_time
        print(f"\n⏱️ Tempo (chat.completions): {elapsed:.2f}s")


if __name__ == "__main__":
    try:
        # run_with_responses_api()
        stream_with_responses_api()
    finally:
        _close_client(client)
