from __future__ import annotations

"""Geração estruturada de respostas usando function-calling."""

from typing import Any, Dict, List
import json

ANSWER_SCHEMA: Dict[str, Any] = {
    "name": "emit_answer",
    "description": "Resposta estruturada e citada",
    "parameters": {
        "type": "object",
        "properties": {
            "diagnostico": {"type": "string"},
            "o_que_fazer_agora": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
            },
            "fundamentos": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
            },
            "checklist": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
            },
            "como_atuaremos": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
            },
            "citacoes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "fonte": {"type": "string", "enum": ["FAISS", "DATAJUD", "BNP"]},
                        "id": {"type": "string"},
                    },
                    "required": ["fonte", "id"],
                },
                "minItems": 3,
            },
        },
        "required": [
            "diagnostico",
            "o_que_fazer_agora",
            "fundamentos",
            "checklist",
            "como_atuaremos",
            "citacoes",
        ],
    },
}

SYSTEM_ANSWER = (
    "Você é advogado. Responda SOMENTE com function_call emit_answer.\n"
    "REGRAS:\n"
    "- Proíba frases genéricas (ex.: 'trata-se de tema cível'). Seja concreto.\n"
    "- Cada fundamento deve estar ANCORADO em algo do contexto RAG (leis/precedentes/trechos).\n"
    "- Verbo no imperativo nos passos ('Notifique', 'Delibere', 'Protocole').\n"
    "- Se houver variantes (Ltda x S.A; TJ x JEF), diga qual se aplica ao frame.\n"
)


def generate_answer(llm: Any, pergunta: str, frame: Dict[str, Any], pack: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Gera resposta final a partir do frame e do contexto recuperado."""
    contexto = "\n\n".join(
        [f"[{i+1}] {h['fonte']}:{h['id']} — {h['trecho'][:480]}" for i, h in enumerate(pack)]
    )
    user_msg = f"""Pergunta: {pergunta}\n\nFrame: {frame}\n\nContexto citável:\n{contexto}\n"""
    resp = llm.client.chat.completions.create(  # type: ignore[attr-defined]
        model=getattr(llm, "chat_model", None),
        messages=[{"role": "system", "content": SYSTEM_ANSWER}, {"role": "user", "content": user_msg}],
        tools=[ANSWER_SCHEMA],
        tool_choice={"type": "function", "function": {"name": "emit_answer"}},
    )
    tool_call = resp.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments or "{}")