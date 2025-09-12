from __future__ import annotations

from typing import Iterable


def is_greeting(text: str) -> bool:
    """Detecção leve de saudações em PT-BR.

    Considera algumas expressões comuns no início da mensagem.
    """
    if not text:
        return False
    txt = text.strip().lower()
    greetings: Iterable[str] = (
       "oi",
        "oie",
        "e aí",
        "iai",
        "olá",
        "ola",
        "bom dia",
        "boa tarde",
        "boa noite",
        "como você está",
        "como voce esta",
        "como vc tá",
        "como vc ta",
        "tudo bem",
        "como anda as coisas",
    )
    return any(txt.startswith(g) for g in greetings)