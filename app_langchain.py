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
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_oci import ChatOCIOpenAI
from oci_openai import OciUserPrincipalAuth

load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


def _print_pretty_json(payload: object) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    try:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    except Exception:
        print(repr(payload))


def _print_usage(payload: object) -> None:
    usage = getattr(payload, "usage_metadata", None) or getattr(payload, "usage", None)
    if usage is None and isinstance(payload, dict):
        usage = payload.get("usage_metadata") or payload.get("usage")
    if usage is None and hasattr(payload, "model_dump"):
        data = payload.model_dump()
        if isinstance(data, dict):
            usage = data.get("usage_metadata") or data.get("usage")
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
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("text"):
                parts.append(part["text"])
        return "".join(parts)
    return ""


client = _build_client()

SYSTEM_PROMPT = "Você é um assistente útil."
USER_PROMPT = "Explique como listar todos os arquivos de um diretório usando Python."

PRINT_RAW = False


def run_with_responses_api() -> None:
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=USER_PROMPT),
    ]

    start_time = time.time()
    try:
        response = client.invoke(messages)
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
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=USER_PROMPT),
    ]

    start_time = time.time()
    try:
        last_usage = None
        if PRINT_RAW:
            for chunk in client.stream(messages):
                _print_pretty_json(chunk)
                last_usage = chunk
        else:
            for chunk in client.stream(messages):
                text = _extract_chunk_text(chunk)
                if text:
                    print(text, end="", flush=True)
                last_usage = chunk
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
