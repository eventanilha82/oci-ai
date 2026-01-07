import json
import os
import time
import warnings

import httpx
from dotenv import load_dotenv
from oci_openai import OciUserPrincipalAuth
from openai import OpenAI

load_dotenv()
warnings.filterwarnings("ignore", message="Pydantic serializer warnings:.*")


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
    usage = getattr(payload, "usage", None)
    if usage is None and isinstance(payload, dict):
        usage = payload.get("usage")
    if usage is None and hasattr(payload, "model_dump"):
        data = payload.model_dump()
        if isinstance(data, dict):
            usage = data.get("usage")
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


def _extract_reasoning_summary(payload: object) -> str | None:
    data = payload
    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
    output = None
    if isinstance(data, dict):
        output = data.get("output") or []
    elif isinstance(data, list):
        output = data
    else:
        return None
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "reasoning":
            continue
        summary = item.get("summary")
        if not isinstance(summary, list):
            continue
        for part in summary:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "summary_text" and part.get("text"):
                return part["text"]
    return None


def _print_summary(payload: object) -> None:
    summary = _extract_reasoning_summary(payload)
    if summary:
        print("\n🧠 Summary:")
        print(summary)


COMPARTMENT_ID = _require_env("OCI_COMPARTMENT_ID")
HTTP_CLIENT_HEADERS = {"CompartmentId": COMPARTMENT_ID}
OCI_BASE_URL = _require_env("OCI_BASE_URL")
OCI_CONFIG_FILE = os.path.expanduser(_require_env("OCI_CONFIG_FILE"))
MODEL_ID = "openai.gpt-oss-120b"


def _build_client() -> OpenAI:
    http_client = httpx.Client(
        auth=OciUserPrincipalAuth(config_file=OCI_CONFIG_FILE),
        headers=HTTP_CLIENT_HEADERS,
    )
    return OpenAI(
        api_key="OCI",
        base_url=OCI_BASE_URL,
        http_client=http_client,
    )


def _close_client(client: OpenAI) -> None:
    http_client = getattr(client, "http_client", None)
    if http_client is not None:
        http_client.close()


client = _build_client()

SYSTEM_PROMPT = "Você é um assistente útil."
USER_PROMPT = "Qual é a resposta para 12 * (3 + 9)?"

PRINT_RAW = False


def run_with_responses_api() -> None:
    start_time = time.time()
    try:
        response = client.responses.create(
            model=MODEL_ID,
            instructions=SYSTEM_PROMPT,
            input=USER_PROMPT,
            reasoning={"summary": "auto"},
        )
        if PRINT_RAW:
            _print_pretty_json(response)
        else:
            print(response.output_text)
        _print_summary(response)
        _print_usage(response)
    except Exception as exc:
        print(f"\n[ERRO Responses create]: {exc}")
    finally:
        elapsed = time.time() - start_time
        print(f"\n⏱️ Tempo (responses.create): {elapsed:.2f}s")


def stream_with_responses_api() -> None:
    start_time = time.time()
    try:
        stream = client.responses.create(
            model=MODEL_ID,
            instructions=SYSTEM_PROMPT,
            input=USER_PROMPT,
            stream=True,
            reasoning={"effort": "low", "summary": "auto"},
            stream_options={"include_usage": True},
        )
        if PRINT_RAW:
            for event in stream:
                _print_pretty_json(event)
                if getattr(event, "type", None) == "response.completed":
                    _print_usage(getattr(event, "response", None))
        else:
            last_usage = None
            for event in stream:
                if getattr(event, "type", None) == "response.output_text.delta":
                    print(event.delta, end="", flush=True)
                elif getattr(event, "type", None) == "response.completed":
                    last_usage = getattr(event, "response", None) or last_usage
            print()
            if last_usage is not None:
                _print_summary(last_usage)
                _print_usage(last_usage)
    except Exception as exc:
        print(f"\n[ERRO Responses stream]: {exc!r}")
    finally:
        elapsed = time.time() - start_time
        print(f"\n⏱️ Tempo (responses.stream): {elapsed:.2f}s")


if __name__ == "__main__":
    try:
        # run_with_responses_api()
        stream_with_responses_api()

    finally:
        _close_client(client)
