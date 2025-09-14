from __future__ import annotations
from typing import Dict
from .case_state import CaseState


class CaseRepository:
    def get(self, chat_id: str) -> CaseState: ...
    def save(self, chat_id: str, state: CaseState) -> None: ...


class InMemoryCaseRepository(CaseRepository):
    """Armazenamento em memória (substitua por Redis/DB no prod)."""

    def __init__(self):
        self._db: Dict[str, CaseState] = {}

    def get(self, chat_id: str) -> CaseState:
        return self._db.setdefault(chat_id, CaseState())

    def save(self, chat_id: str, state: CaseState) -> None:
        self._db[chat_id] = state


# Exemplo: substituto baseado em Redis (opcional)
try:
    import redis  # type: ignore
    import json

    class RedisCaseRepository(CaseRepository):
        def __init__(self, url: str):
            self.r = redis.from_url(url)
            self.KEY = "case:state:"

        def get(self, chat_id: str) -> CaseState:
            raw = self.r.get(self.KEY + chat_id)
            if not raw:
                return CaseState()
            data = json.loads(raw)
            cs = CaseState()
            cs.merge(data)  # fill
            # docs e asked_slots precisam de merge completo
            if isinstance(data.get("docs"), dict):
                cs.docs = {**cs.docs, **data["docs"]}
            if isinstance(data.get("asked_slots"), list):
                cs.asked_slots = set(data["asked_slots"])
            return cs

        def save(self, chat_id: str, state: CaseState) -> None:
            data = state.to_prompt_facts()
            # manter asked_slots também
            data["asked_slots"] = list(state.asked_slots)
            self.r.set(self.KEY + chat_id, json.dumps(data, ensure_ascii=False))
except Exception:  # redis não instalado
    pass
