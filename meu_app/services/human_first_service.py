from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from typing import Optional


def _norm(s: str) -> str:
    """Normalise text by removing accents and collapsing whitespace."""

    normalized = "".join(
        ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn"
    )
    return re.sub(r"\s+", " ", (normalized or "").strip().lower())

_GREET = re.compile(r"\b(oi|ola|olá|oie|opa|e ai|hey|hi|hello|bom dia|boa tarde|boa noite)\b")
_SMALL_TALK = re.compile(r"(tudo bem\??|como vai\??|como vc ta\??|como voce esta\??)")
_HELP_OPENERS = re.compile(
    r"(pode me ajudar|preciso de ajuda|me ajuda|me tira? uma duvida|tenho uma duvida|posso tirar uma duvida)"
)

def detect_micro_intent(text: str) -> str:
    """Return a simple classification for very short messages.

    The recognised intents are ``greeting``, ``smalltalk`` and ``help_opener``.
    Any other text is classified as ``other``.
    """
    n = _norm(text)
    tokens = n.split()
    short = len(tokens) <= 10  # only micro-openings are considered
    if short and _GREET.search(n) and not any(w in n for w in ["processo", "contrato", "prazo"]):
        # plain greeting
        return "greeting"
    if short and _SMALL_TALK.search(n):
        return "smalltalk"
    if short and _HELP_OPENERS.search(n):
        return "help_opener"
    return "other"


class HumanFirstService:
    """Very small service that replies to opening messages.

    It uses :func:`detect_micro_intent` to decide whether the user's first
    message should be answered with a greeting.  The actual greeting text is
    delegated to :func:`generate_human_greeting`, which offers a deterministic
    message and does not require a real LLM implementation.
    """

    def __init__(self, llm: Optional[object], brand: str):
        self.llm = llm
        self.brand = brand

    def handle_opening(self, text: str, sender_name: Optional[str]) -> Optional[str]:
        """Return a friendly greeting or ``None``.

        ``sender_name`` is optional because the very first message may come
        without any contact information.
        """

        intent = detect_micro_intent(text or "")
        if intent in {"greeting", "smalltalk", "help_opener"}:
            from .greeting_service import generate_human_greeting

            return generate_human_greeting(
                self.llm,
                name=sender_name,
                brand=self.brand,
                now_local=datetime.now(),
            )
        return None


__all__ = ["HumanFirstService", "detect_micro_intent"]
