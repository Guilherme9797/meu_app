from __future__ import annotations

"""Classificador e extrator de metadados jurídicos via function-calling."""

from typing import Any, Dict
import json

# Esquema JSON para retorno estruturado do frame do caso
FRAME_SCHEMA: Dict[str, Any] = {
    "name": "emit_frame",
    "description": "Enquadra caso jurídico em múltiplos domínios e institutos",
    "parameters": {
        "type": "object",
        "properties": {
            "dominios": {"type": "array", "items": {"type": "string"}},
            "institutos": {"type": "array", "items": {"type": "string"}},
            "atos_centrais": {"type": "array", "items": {"type": "string"}},
            "bens_relacionados": {"type": "array", "items": {"type": "string"}},
            "foro_indicado": {"type": "string"},
            "palavras_chave": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["dominios", "institutos", "palavras_chave"],
    },
}

SYSTEM_FRAME = (
    "Você é um jurista classificando casos.\n"
    "Responda só via function_call emit_frame.\n"
    "- Domínios possíveis: civil, consumidor, empresarial, penal, processual_civil,"
    " processual_penal, tributário, previdenciário, ambiental, administrativo, trabalho,"
    " processual_trabalho, família, sucessões, imobiliário.\n"
    "- Institutos: use termos canônicos (ex.: 'sócio remisso', 'difamação',"
    " 'adjudicação compulsória', 'negativação indevida', 'habeas corpus').\n"
    "- Extraia atos (notificar, ajuizar, registrar, etc.) e bens (imóvel, quotas, veículo, crédito)."
)

def frame_case(llm: Any, pergunta: str) -> Dict[str, Any]:
    """Gera o enquadramento jurídico (frame) para a pergunta do cliente."""
    messages = [
        {"role": "system", "content": SYSTEM_FRAME},
        {"role": "user", "content": pergunta},
    ]
    # Usa a API de chat com function-calling para obter JSON estruturado
    resp = llm.client.chat.completions.create(  # type: ignore[attr-defined]
        model=getattr(llm, "chat_model", None),
        messages=messages,
        tools=[FRAME_SCHEMA],
        tool_choice={"type": "function", "function": {"name": "emit_frame"}},
    )
    tool_call = resp.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments or "{}")