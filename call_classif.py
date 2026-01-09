import json
import os
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()

# =========================================================
# 1. CONTRATO DE SAÍDA (Pydantic)
# =========================================================


class MotivoContato(BaseModel):
    fala: str = Field(description="Fala original do cliente")
    motivo_principal: Literal[
        "FATURAMENTO",
        "COBRANCA",
        "SUPORTE_TECNICO",
        "CANCELAMENTO",
        "RETENCAO",
        "CONTRATACAO",
        "INFORMACOES_GERAIS",
        "RECLAMACAO",
        "OUTROS",
    ]
    confianca: float = Field(ge=0.0, le=1.0)
    justificativa_curta: str = Field(max_length=240)


# =========================================================
# 2. BLOCO DE FEW-SHOTS (⬅️ EDITÁVEL POR VOCÊ)
# =========================================================
# ➜ AQUI você define exemplos comuns de negócio
# ➜ Texto do cliente + classificação esperada

FEW_SHOTS_EXEMPLOS = """
[
  {
    "fala": "Minha fatura veio mais cara que o plano contratado.",
    "motivo_principal": "FATURAMENTO",
    "confianca": 0.95,
    "justificativa_curta": "Questionamento sobre valor da fatura."
  },
  {
    "fala": "Estou sendo cobrado mesmo já tendo pago.",
    "motivo_principal": "COBRANCA",
    "confianca": 0.94,
    "justificativa_curta": "Cobrança indevida após pagamento."
  },
  {
    "fala": "A internet parou de funcionar hoje cedo.",
    "motivo_principal": "SUPORTE_TECNICO",
    "confianca": 0.97,
    "justificativa_curta": "Falha técnica no serviço."
  },
  {
    "fala": "Quero cancelar meu plano agora.",
    "motivo_principal": "CANCELAMENTO",
    "confianca": 0.99,
    "justificativa_curta": "Solicitação direta de cancelamento."
  },
  {
    "fala": "Se não fizerem um desconto, vou cancelar.",
    "motivo_principal": "RETENCAO",
    "confianca": 0.88,
    "justificativa_curta": "Cliente condiciona permanência a desconto."
  },
  {
    "fala": "Quero contratar um plano melhor.",
    "motivo_principal": "CONTRATACAO",
    "confianca": 0.96,
    "justificativa_curta": "Intenção de contratar novo plano."
  },
  {
    "fala": "Qual o horário de atendimento?",
    "motivo_principal": "INFORMACOES_GERAIS",
    "confianca": 0.93,
    "justificativa_curta": "Solicitação de informação geral."
  },
  {
    "fala": "Já liguei várias vezes e ninguém resolve.",
    "motivo_principal": "RECLAMACAO",
    "confianca": 0.92,
    "justificativa_curta": "Insatisfação com atendimento."
  },
  {
    "fala": "Só estou ligando para registrar.",
    "motivo_principal": "OUTROS",
    "confianca": 0.55,
    "justificativa_curta": "Intenção não clara."
  }
]
"""


# =========================================================
# 3. PROMPT DE SISTEMA (REGRAS RÍGIDAS)
# =========================================================

SYSTEM_PROMPT = f"""
Você é um classificador corporativo de motivos de contato de call center.

REGRAS:
- Classifique apenas UM motivo principal.
- NÃO crie novos rótulos.
- Se houver ambiguidade real, use "OUTROS".
- Se a confiança for menor que 0.6, use "OUTROS".
- Responda com UM ÚNICO objeto JSON válido e nada além disso.
- NÃO use Markdown, NÃO use blocos de código e NÃO use ``` em hipótese alguma.
- O output deve começar com '{{' e terminar com '}}'.
- Use exatamente as chaves: fala, motivo_principal, confianca, justificativa_curta.
- "fala" deve ser exatamente a mesma recebida na entrada.
- justificativa_curta deve ter no máximo 1 frase.

Valores permitidos para motivo_principal:
FATURAMENTO, COBRANCA, SUPORTE_TECNICO, CANCELAMENTO, RETENCAO,
CONTRATACAO, INFORMACOES_GERAIS, RECLAMACAO, OUTROS.

Critério de confiança:
- 0.90–1.00 → intenção explícita
- 0.70–0.89 → intenção clara
- 0.60–0.69 → intenção provável
- <0.60 → OUTROS

Exemplos oficiais (JSON):
{FEW_SHOTS_EXEMPLOS}
"""


# =========================================================
# 4. FUNÇÃO DE CLASSIFICAÇÃO
# =========================================================


def classificar_motivo(transcricao_cliente: str) -> MotivoContato | None:
    api_key = os.environ.get("LITELLM_API_KEY")
    if not api_key:
        raise ValueError("LITELLM_API_KEY nao configurada no .env")
    client = OpenAI(api_key=api_key, base_url="http://localhost:4000")

    user_prompt = json.dumps({"fala": transcricao_cliente}, ensure_ascii=False)

    try:
        response = client.chat.completions.parse(
            model="gemini-2-5-flash",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=MotivoContato,
            temperature=0,
        )
        return response.choices[0].message.parsed
    except Exception:
        print("Nao foi possivel fazer a classificacao.")
        return None


# =========================================================
# 5. EXEMPLO DE USO
# =========================================================

if __name__ == "__main__":
    texto = "Se continuar esse valor alto, vou cancelar meu plano."
    resultado = classificar_motivo(texto)
    if resultado is not None:
        print(resultado.model_dump())

    frases = [
        "Minha fatura veio com um valor errado.",
        "Fui cobrado duas vezes no cartao.",
        "A internet esta caindo toda hora.",
        "Quero cancelar agora mesmo.",
        "Se nao reduzirem, vou cancelar.",
        "Quero contratar um plano mais rapido.",
        "Qual o horario de atendimento?",
        "Ja liguei varias vezes e ninguem resolve.",
        "So queria registrar um elogio.",
        "Minha linha esta sem sinal.",
        "A fatura esta com juros indevidos.",
        "Estou com cobranca de servico que nao assinei.",
        "Preciso de suporte para configurar o roteador.",
        "Quero saber se tem fidelidade.",
        "Quero mudar meu plano atual.",
        "O tecnico nao compareceu na visita.",
        "Meu desconto nao apareceu na fatura.",
        "Quero reativar o servico cancelado.",
        "Posso falar com um supervisor?",
        "Preciso de segunda via da fatura.",
    ]

    print("\n--- Lote com 20 classificacoes ---")
    for fala in frases:
        item = classificar_motivo(fala)
        if item is None:
            print({"fala": fala, "erro": "Nao foi possivel fazer a classificacao."})
        else:
            print(item.model_dump())
