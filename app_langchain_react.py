import json
import os
import time
import warnings
from datetime import datetime

warnings.filterwarnings(
    "ignore",
    message=(
        "Core Pydantic V1 functionality isn't compatible with Python 3.14 or "
        "greater\\."
    ),
)

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_oci import ChatOCIOpenAI
from oci_openai import OciUserPrincipalAuth

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


def get_current_time() -> str:
    """Get the current time."""
    return datetime.now().isoformat(timespec="seconds")


client = _build_client()

SYSTEM_PROMPT = "Você é um assistente útil."
USER_PROMPT = "Que horas são agora? Me responda com um cumprimento cordial conforme o horário. Me conte uma história usando esse horário."

PRINT_RAW = False

graph = create_agent(
    model=client,
    tools=[get_current_time],
    system_prompt=SYSTEM_PROMPT,
)


def run_with_responses_api() -> None:
    messages = [
        HumanMessage(content=USER_PROMPT),
    ]

    start_time = time.time()
    try:
        response = graph.invoke({"messages": messages})
        if PRINT_RAW:
            _print_pretty_json(response)
        else:
            print(_extract_chunk_text(response))
        _print_usage(response)
    except Exception as exc:
        print(f"\n[ERRO Responses create]: {exc}")
    finally:
        elapsed = time.time() - start_time
        print(f"\n⏱️ Tempo (chat.completions create): {elapsed:.2f}s")


def stream_with_responses_api() -> None:
    messages = [
        HumanMessage(content=USER_PROMPT),
    ]

    start_time = time.time()
    try:
        last_usage = None
        for chunk in graph.stream({"messages": messages}, stream_mode="messages"):
            text = _extract_chunk_text(chunk)
            if text:
                print(text, end="", flush=True)
            if getattr(chunk, "usage_metadata", None) or getattr(chunk, "usage", None):
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
        print()
        if last_usage is not None:
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
