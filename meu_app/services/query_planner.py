from __future__ import annotations
from typing import Any, Dict, List
import json
import re

SCHEMA = {
    "name": "emit_queries",
    "description": "Planeja consultas diversificadas para RAG jurídico (lexicais, sinônimos, estatutos/artigos, booleanos).",
    "parameters": {
        "type": "object",
        "properties": {
            "lexicais": {"type": "array", "items": {"type": "string"}},
            "sinonimos": {"type": "array", "items": {"type": "string"}},
            "estatutos": {"type": "array", "items": {"type": "string"}},
            "booleanas_datajud": {"type": "array", "items": {"type": "string"}},
            "booleanas_bnp": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["lexicais", "sinonimos"],
    },
}

SYSTEM = (
    "Você é um planejador de consultas jurídicas. NÃO responda o caso.\n"
    "Gere listas de termos/consultas para recuperar jurisprudência, doutrina e lei:\n"
    "- 'lexicais': 6–12 termos/frações de frase do problema.\n"
    "- 'sinonimos': 6–12 variações, termos usuais, erros comuns de grafia.\n"
    "- 'estatutos': artigos/leis CÓDIGO+NÚMERO (ex.: 'CC 1.417', 'CC 1.418', 'LRP 216-B', 'CPC 497', 'Lei 9.514/97').\n"
    "- 'booleanas_datajud'/'booleanas_bnp': 3–6 consultas com aspas, OR/AND, coringas, campos (quando fizer sentido).\n"
    "Se o frame indicar imóvel pago e recusa de outorga, inclua adjudicação compulsória e dispositivos correlatos.\n"
)


def plan_queries(llm: Any, pergunta: str, frame: Dict[str, Any], concept_terms: List[str]) -> Dict[str, List[str]]:
    seeds = list(set((frame.get("palavras_chave") or []) + (frame.get("institutos") or []) + concept_terms))
    seeds_txt = ", ".join(seeds[:30])
    user = f"Pergunta: {pergunta}\nFrame: {frame}\nSeeds: {seeds_txt}\n"
    resp = llm.client.chat.completions.create(
        model=getattr(llm, "chat_model", None),
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        tools=[SCHEMA],
        tool_choice={"type": "function", "function": {"name": "emit_queries"}},
    )
    tool_call = resp.choices[0].message.tool_calls[0]
    out = json.loads(tool_call.function.arguments or "{}")

    # limpeza básica
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip()).lower()

    for k in ["lexicais", "sinonimos", "estatutos", "booleanas_datajud", "booleanas_bnp"]:
        out[k] = [norm(t) for t in out.get(k, []) if t and isinstance(t, str)]

    return out