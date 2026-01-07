import json
import os
import time

import httpx
from dotenv import load_dotenv
from oci_openai import OciUserPrincipalAuth
from openai import OpenAI

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


COMPARTMENT_ID = _require_env("OCI_COMPARTMENT_ID")
HTTP_CLIENT_HEADERS = {"CompartmentId": COMPARTMENT_ID}
OCI_BASE_URL = _require_env("OCI_BASE_URL")
OCI_CONFIG_FILE = os.path.expanduser(_require_env("OCI_CONFIG_FILE"))
MODEL_ID = _require_env("OCI_MODEL_ID")


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
USER_PROMPT = "Explique como listar todos os arquivos de um diretório usando Python."

PRINT_RAW = False


def stream_with_chat_completions() -> None:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT},
    ]

    start_time = time.time()
    try:
        stream = client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )

        if PRINT_RAW:
            for chunk in stream:
                _print_pretty_json(chunk)
        else:
            last_usage = None
            for chunk in stream:
                if not chunk.choices:
                    last_usage = getattr(chunk, "usage", None) or last_usage
                    continue
                if (
                    hasattr(chunk.choices[0].delta, "content")
                    and chunk.choices[0].delta.content
                ):
                    text = chunk.choices[0].delta.content
                    print(text, end="", flush=True)
            print()
            if last_usage is not None:
                _print_usage({"usage": last_usage})
    except Exception as exc:
        print(f"\n[ERRO Completions]: {exc}")
    finally:
        elapsed = time.time() - start_time
        print(f"\n⏱️ Tempo (chat.completions): {elapsed:.2f}s")


def run_with_chat_completions() -> None:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT},
    ]

    start_time = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
        )

        if PRINT_RAW:
            _print_pretty_json(response)
        else:
            print(response.choices[0].message.content)
        _print_usage(response)
    except Exception as exc:
        print(f"\n[ERRO Completions create]: {exc}")
    finally:
        elapsed = time.time() - start_time
        print(f"\n⏱️ Tempo (chat.completions create): {elapsed:.2f}s")


def run_with_responses_api() -> None:
    start_time = time.time()
    try:
        response = client.responses.create(
            model=MODEL_ID,
            instructions=SYSTEM_PROMPT,
            input=USER_PROMPT,
        )
        if PRINT_RAW:
            _print_pretty_json(response)
        else:
            print(response.output_text)
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
        # run_with_chat_completions()
        # stream_with_chat_completions()
    finally:
        _close_client(client)
