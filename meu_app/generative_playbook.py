from dataclasses import dataclass
from typing import Dict, List
from datetime import datetime

from .llm import llm_json  # wrapper seu para OpenAI -> retorna JSON validado

PLAYBOOK_SCHEMA = {
  "type": "object",
  "properties": {
    "area": {"type": "string"},
    "subtype": {"type": "string"},
    "goals": {"type": "array", "items": {"type": "string"}},
    "risks": {"type": "array", "items": {"type": "string"}},
    "required_slots": {"type": "array", "items": {"type": "string"}},
    "questions": {"type": "object", "additionalProperties": {"type": "string"}},
    "pricing_services": {"type": "array", "items": {"type": "string"}},  # nomes de serviços (ex.: "Consulta Estratégica", "Defesa Prévia", "Audiência JECRIM")
    "cta": {"type": "string"}
  },
  "required": ["required_slots", "questions", "pricing_services"]
}

SYSTEM_PROMPT = """Você é um assistente jurídico-vendedor que gera um playbook objetivo para qualquer área do Direito no Brasil.
Retorne APENAS JSON no schema combinado. Princípios:
- Pergunte apenas o essencial para decidir o próximo passo.
- Produza 'required_slots' CURTOS e gerais (ex.: 'prazo', 'documentos', 'data_audiencia', 'tipo_beneficio', 'contrato', 'protocolo', 'orçamento').
- 'questions': mapeie cada slot a UMA pergunta direta e leiga.
- 'pricing_services': 2 a 4 serviços canônicos que representem a entrega inicial do caso (ex.: 'Consulta Estratégica', 'Defesa Prévia', 'Audiência JECRIM', 'Recurso Administrativo', 'Ação Declaratória', etc.).
- 'cta' deve ser curto e de fechamento (ex.: 'Posso iniciar hoje. Prefere começar pelo pacote essencial ou intermediário?').
Não dê conselhos médicos/financeiros. Foque na condução jurídica e comercial."""

USER_TEMPLATE = """Mensagem do cliente:
---
{user_text}
---
Contexto já conhecido (resumo sucinto, se houver):
{context_brief}

Agora gere o playbook no JSON pedido.
"""

@dataclass
class Playbook:
    area: str = ""
    subtype: str = ""
    goals: List[str] = None
    risks: List[str] = None
    required_slots: List[str] = None
    questions: Dict[str, str] = None
    pricing_services: List[str] = None
    cta: str = "Posso iniciar hoje. Prefere começar pelo plano essencial ou intermediário?"
    created_at: str = ""
    version: int = 1

def brief_from_case(case) -> str:
    bits = []
    if getattr(case, "deadline", None):
        bits.append(f"prazo/audiência: {case.deadline}")
    if getattr(case, "area", None) or getattr(case, "subtype", None):
        bits.append(f"área/subtipo: {case.area}/{case.subtype}")
    if getattr(case, "slots", None):
        answered = ", ".join(sorted(k for k in getattr(case, "answered", [])))
        if answered:
            bits.append(f"slots: {answered}")
    return " | ".join(bits) if bits else "—"

def generate_playbook(user_text: str, case) -> Playbook:
    payload = USER_TEMPLATE.format(user_text=user_text, context_brief=brief_from_case(case))
    data = llm_json(system=SYSTEM_PROMPT, user=payload, schema=PLAYBOOK_SCHEMA)
    pb = Playbook(
        area=data.get("area",""),
        subtype=data.get("subtype",""),
        goals=data.get("goals",[]) or [],
        risks=data.get("risks",[]) or [],
        required_slots=data.get("required_slots",[]) or [],
        questions=data.get("questions",{}) or {},
        pricing_services=data.get("pricing_services",[]) or [],
        cta=data.get("cta","Posso iniciar hoje. Prefere começar pelo plano essencial ou intermediário?"),
        created_at=datetime.utcnow().isoformat(),
        version=1
    )
    # normalização mínima
    pb.required_slots = [s.strip().lower().replace(" ", "_") for s in pb.required_slots]
    pb.questions = { (k.strip().lower().replace(" ","_")): v for k,v in pb.questions.items() }
    return pb