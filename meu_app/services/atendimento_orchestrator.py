from __future__ import annotations

from typing import Any, Dict, List
from ..nlu import UniversalInterpreter, LegalIntent
from .rag import search_all
from .generator import generate_answer
from .guardrails import refine_if_needed

class AtendimentoOrchestrator:
    """High level orchestrator for legal assistance."""

    def __init__(self, llm: Any, pattern_dir: str, *, topk_each: int = 6, max_qterms: int = 16) -> None:
        self.llm = llm
        self.topk_each = topk_each
        self.max_qterms = max_qterms
        self.interpreter = UniversalInterpreter(pattern_dir=pattern_dir)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _intent_to_qterms(self, intent: LegalIntent) -> List[str]:
        qterms: List[str] = []
        for seq in [intent.keywords, intent.topics, intent.entities, intent.requests]:
            for token in seq:
                token = token.strip()
                if len(token) < 3:
                    continue
                if token not in qterms:
                    qterms.append(token)
                if len(qterms) >= self.max_qterms:
                    break
            if len(qterms) >= self.max_qterms:
                break
        return qterms

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------
    def atender(self, pergunta: str) -> Dict[str, Any]:
        intent = self.interpreter.interpret(pergunta)
        qterms = self._intent_to_qterms(intent)
        frame = intent.to_dict()
        pack = search_all(self.llm, qterms, frame, topk_each=self.topk_each, query_text=pergunta)
        answer = generate_answer(self.llm, pergunta, frame, pack)
        answer = refine_if_needed(self.llm, pergunta, frame, pack, answer)
        answer["_debug"] = {
            "intent": frame,
            "qterms": qterms,
            "ctx": pack,
        }
        return answer


# Utility function for quick usage ------------------------------------------------

def atender(
    llm: Any,
    pergunta: str,
    *,
    pattern_dir: str,
    topk_each: int = 6,
    max_qterms: int = 16,
) -> Dict[str, Any]:
    """Convenience wrapper used by service handlers."""
    orch = AtendimentoOrchestrator(llm, pattern_dir, topk_each=topk_each, max_qterms=max_qterms)
    return orch.atender(pergunta)