import base64
import json
import os
import time

import httpx
from dotenv import load_dotenv
from oci_openai import OciOpenAI, OciUserPrincipalAuth
from openai import OpenAI

load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


def encode_file(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


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
CONVERSATION_STORE_ID = _require_env("OCI_CONVERSATION_STORE_ID")
HTTP_CLIENT_HEADERS = {
    "CompartmentId": COMPARTMENT_ID,
    "opc-compartment-id": COMPARTMENT_ID,
    "opc-conversation-store-id": CONVERSATION_STORE_ID,
}
# OCI_BASE_URL = _require_env("OCI_BASE_URL")
OCI_BASE_URL = (
    "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com/openai/v1"
)
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

SYSTEM_PROMPT = "Você é um especialista em analises."
USER_PROMPT = "O que você pode me dizer sobre o conteúdo deste PDF?"
BASE64_PDF = encode_file("A-ARTE-DA-GUERRA.pdf")

PRINT_RAW = False


def run_with_responses_api() -> None:
    start_time = time.time()
    try:
        response = client.responses.create(
            model="openai.gpt-5",
            # model=MODEL_ID,
            instructions=SYSTEM_PROMPT,
            reasoning={"effort": "low", "summary": "auto"},
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": USER_PROMPT},
                        {
                            "type": "input_file",
                            "filename": "filename.pdf",
                            "file_data": f"data:application/pdf;base64,{BASE64_PDF}",
                        },
                    ],
                }
            ],
            # input=[
            #     {
            #         "role": "user",
            #         "content": [
            #             {"type": "input_text", "text": USER_PROMPT},
            #             {
            #                 "type": "input_file",
            #                 "file_url": "https://www.berkshirehathaway.com/letters/2024ltr.pdf",
            #             },
            #         ],
            #     }
            # ],
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
            model="openai.gpt-5",
            instructions=SYSTEM_PROMPT,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": USER_PROMPT},
                        {
                            "type": "input_file",
                            "file_url": "https://www.berkshirehathaway.com/letters/2024ltr.pdf",
                        },
                    ],
                }
            ],
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
        run_with_responses_api()
        # stream_with_responses_api()

    finally:
        _close_client(client)
