from __future__ import annotations
import re
import unicodedata


def _norm(s: str) -> str:
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", (s or "").strip().lower())

_GREET = re.compile(r"\b(oi|ola|olá|oie|opa|e ai|hey|hi|hello|bom dia|boa tarde|boa noite)\b")
_SMALL_TALK = re.compile(r"(tudo bem\??|como vai\??|como vc ta\??|como voce esta\??)")
_HELP_OPENERS = re.compile(
    r"(pode me ajudar|preciso de ajuda|me ajuda|me tira? uma duvida|tenho uma duvida|posso tirar uma duvida)"
)

def detect_micro_intent(text: str) -> str:
    """
    Retorna: 'greeting' | 'smalltalk' | 'help_opener' | 'other'
    """
    n = _norm(text)
    tokens = n.split()
    short = len(tokens) <= 10  # só micro-aberturas
    if short and _GREET.search(n) and not any(w in n for w in ["processo", "contrato", "prazo"]):
        # saudação pura
        return "greeting"
    if short and _SMALL_TALK.search(n):
        return "smalltalk"
    if short and _HELP_OPENERS.search(n):
        return "help_opener"
    return "other"