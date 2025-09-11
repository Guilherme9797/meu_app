from __future__ import annotations

from typing import Any, Dict, List
from .legal_frame import frame_case
from .concepts import ConceptBank
from .query_planner import plan_queries
from .rag import search_all
from .generator import generate_answer
from .guardrails import refine_if_needed

def atender(llm: Any, pergunta: str, taxonomies: List[Dict], topk_each: int = 6) -> Dict[str, Any]:
    # 1) Frame
    frame = frame_case(llm, pergunta)
    # 2) Concept expansion (melhorado) + Planner
    bank = ConceptBank(taxonomies)
    concept_terms = bank.expand(frame, pergunta=pergunta)

    qplan = plan_queries(llm, pergunta, frame, concept_terms)

    # 3) Rodada 1: lexicais + sinônimos
    qterms_round1 = list(dict.fromkeys((qplan.get("lexicais", []) + qplan.get("sinonimos", []) + concept_terms)))
    pack = search_all(llm, qterms_round1, frame, topk_each=topk_each, query_text=pergunta)

    # 4) Se fraco, rodada 2: estatutos e booleanas
    if len(pack) < 6:
        qterms_round2 = list(dict.fromkeys(qterms_round1 + qplan.get("estatutos", []) + qplan.get("booleanas_datajud", []) + qplan.get("booleanas_bnp", [])))
        pack = search_all(llm, qterms_round2, frame, topk_each=topk_each, query_text=pergunta)

    # 5) Se ainda fraco, alonga com n-grams (ConceptBank já faz) e reitera
    if len(pack) < 6:
        extra = [t for t in concept_terms if len(t.split()) >= 2]
        qterms_round3 = list(dict.fromkeys(qterms_round2 + extra))
        pack = search_all(llm, qterms_round3, frame, topk_each=topk_each, query_text=pergunta)

    # 6) Geração + refine com guardrails
    answer = generate_answer(llm, pergunta, frame, pack)
    answer = refine_if_needed(llm, pergunta, frame, pack, answer)
    # 7) Anexa debug
    answer["_debug"] = {
        "frame": frame,
        "qplans": qplan,
        "qterms": (qterms_round1[:20] if len(pack) >= 6 else (qterms_round3[:20] if 'qterms_round3' in locals() else qterms_round2[:20])),
        "ctx": pack,
    }
    return answer