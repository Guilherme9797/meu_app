from __future__ import annotations

"""Mecanismos simples anti-respostas genéricas e refinamento."""

from typing import Any, Dict

from .generator import generate_answer

ANTI_GENERIC = [
    "trata-se de tema cível",
    "demanda envolve responsabilidade civil",
    "documentos pessoais: rg, cpf",
]

def grade(answer: Dict[str, Any], pergunta: str) -> float:
    """Atribui nota à resposta com base em heurísticas de especificidade."""
    txt = " ".join(
        [
            answer.get("diagnostico", ""),
            " ".join(answer.get("o_que_fazer_agora", [])),
            " ".join(answer.get("fundamentos", [])),
        ]
    ).lower()
    penal = sum(1 for s in ANTI_GENERIC if s in txt) * 0.25
    cites = len(answer.get("citacoes", []))
    steps = len(answer.get("o_que_fazer_agora", []))
    score = 1.0 - penal + 0.1 * (cites >= 3) + 0.1 * (steps >= 4)
    return max(0.0, min(1.2, score))


def refine_if_needed(llm: Any, pergunta: str, frame: Dict[str, Any], pack: list, answer: Dict[str, Any]) -> Dict[str, Any]:
    """Regera resposta quando nota abaixo do limiar."""
    if grade(answer, pergunta) >= 0.8:
        return answer
    feedback = (
        "Sua resposta ficou genérica. Inclua:\n"
        "- Órgão/foro indicado ao frame,\n"
        "- Prazos (quando aplicável),\n"
        "- Ato processual/administrativo específico,\n"
        "- Diferenças relevantes (ex.: Ltda vs S.A; JEF vs Justiça Estadual),\n"
        "- Cite pelo menos 3 fontes distintas do contexto.\n"
    )
    return generate_answer(llm, pergunta + "\n\n" + feedback, frame, pack)