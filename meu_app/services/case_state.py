from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, Set
from datetime import datetime


@dataclass
class CaseState:
    """Memória persistente por conversa/caso (intent-agnostic).
    Expanda os slots conforme as suas áreas (previdenciário, civil, etc.).
    """

    # Domínio geral (inferido de forma leve)
    domain: Optional[str] = None  # previdenciario, civil, penal, etc.

    # --- Exemplo de slots para Previdenciário ---
    benefit_type: Optional[str] = None  # auxílio-doença, BPC, etc.
    pericia_date: Optional[str] = None  # dd/mm/aaaa
    denial_date: Optional[str] = None
    science_date: Optional[str] = None  # data de ciência
    cid: Optional[str] = None           # ex.: F33.1
    incapacity: Optional[str] = None    # temporária/permanente

    docs: Dict[str, bool] = field(default_factory=dict)  # {"relatorio": True, "decisao": True, "cnis": False}

    asked_slots: Set[str] = field(default_factory=set)   # slots já perguntados
    updated_at: Optional[str] = None

    def merge(self, new: Dict[str, Any]):
        """Preenche somente campos vazios e faz OR para docs."""
        for k, v in (new or {}).items():
            if k == "docs" and isinstance(v, dict):
                self.docs = {**self.docs, **{dk: bool(dv) for dk, dv in v.items()}}
            elif getattr(self, k, None) in (None, "") and v:
                setattr(self, k, v)
        self.updated_at = datetime.utcnow().isoformat()

    def mark_asked(self, slot: str):
        if slot:
            self.asked_slots.add(slot)

    def to_prompt_facts(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("asked_slots", None)
        d.pop("updated_at", None)
        return d
