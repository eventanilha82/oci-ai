import os
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def main() -> None:
    api_key = os.environ.get("LITELLM_API_KEY")
    if not api_key:
        raise ValueError("LITELLM_API_KEY nao configurada no .env")
    client = OpenAI(api_key=api_key, base_url="http://localhost:4000")

    started_at = time.perf_counter()
    response = client.chat.completions.create(
        model="gemini-2-5-flash-lite",
        messages=[
            {"role": "system", "content": "Voce e um assistente util."},
            {
                "role": "user",
                "content": "Explique em portugues, em duas frases, o que e o LiteLLM.",
            },
        ],
    )
    elapsed = time.perf_counter() - started_at

    print("Resposta:")
    print(response.choices[0].message.content)
    if response.usage:
        print(
            f"Usage — prompt: {response.usage.prompt_tokens}, completion: {response.usage.completion_tokens}, total: {response.usage.total_tokens}"
        )
    print(f"Elapsed: {elapsed:.3f}s")


if __name__ == "__main__":
    main()
