from typing import Dict, Any, List
from meu_app.utils.openai_client import LLM

EXTRACTION_SYS = """Você extrai slots para um roteiro de WhatsApp jurídico.
Responda APENAS JSON válido conforme o esquema."""

EXTRACTION_USER_TMPL = """Texto do cliente:
---
{user_text}
---
Gere JSON com:
- user_problem (string)
- risk_benefit (string, 1 frase)
- low_friction_step (string)
- escalation_step (string)
- triage_questions (array de 2 a 4 strings, curtas)
- social_proof (string ou vazio)
- docs_to_request (array de 2 a 5 strings)
- price_anchor (string ou vazio)"""

def extract_slots(llm: LLM, user_text: str) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": EXTRACTION_SYS},
        {"role": "user", "content": EXTRACTION_USER_TMPL.format(user_text=user_text)},
    ]
    resp = llm.chat(messages=messages, temperature=0.2, top_p=0.9)
    # sanear JSON:
    import json, re

    txt = resp.strip()
    txt = re.sub(r"^```json|```$", "", txt, flags=re.MULTILINE).strip()
    try:
        data = json.loads(txt)
    except Exception:
        # fallback mínimo
        data = {
            "user_problem": "não especificado",
            "risk_benefit": "Agir agora evita custos e perda de prazos.",
            "low_friction_step": "Análise rápida dos documentos e orientação inicial.",
            "escalation_step": "Se necessário, medida judicial com pedido urgente.",
            "triage_questions": [
                "Qual é o documento/notificação que você recebeu?",
                "Quando aconteceu o fato?",
                "Você tem comprovantes (pagamento, mensagens, fotos)?",
            ],
            "social_proof": "",
            "docs_to_request": [
                "Documento/notificação",
                "Comprovantes",
                "Identificação e endereço",
            ],
            "price_anchor": "",
        }
    return data