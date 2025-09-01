from __future__ import annotations

import unicodedata
from typing import Dict

# Phrases that indicate the user has confirmed the issue is resolved.
_RESOLUTION_PHRASES = [
    "obrigado",  # thanks
    "obrigada",
    "valeu",
    "resolveu",
    "resolvido",
    "resolvida",
    "esta resolvido",
    "pode encerrar",
    "pode fechar",
    "sem mais duvidas",
    "nao tenho mais duvidas",
    "era isso",
    "so isso",
    "tudo certo",
    "tudo bem agora",
    "tudo resolvido",
    "deu certo",
]


def _normalize(text: str) -> str:
    """Return a lowercase ascii representation of *text*."""
    text = text or ""
    # remove accents/diacritics and normalise casing
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )


def is_resolution_confirmation(text: str) -> bool:
    """Return ``True`` if ``text`` confirms the issue is resolved.

    The check is accent-insensitive and searches for any of the phrases in
    ``_RESOLUTION_PHRASES``.
    """
    norm = _normalize(text)
    return any(phrase in norm for phrase in _RESOLUTION_PHRASES)


# In-memory repository for session flags.
# Keys are session identifiers (e.g., phone numbers) and values are dictionaries
# with arbitrary session metadata.
sess_repo: Dict[str, Dict[str, bool]] = {}


def handle_incoming(session_id: str, message: str, *, repo: Dict[str, Dict[str, bool]] | None = None) -> str:
    """Handle an incoming ``message`` for ``session_id``.

    When the message matches ``is_resolution_confirmation`` the session is marked
    as resolved in ``repo`` and a closing response is returned.
    """
    if repo is None:
        repo = sess_repo

    if is_resolution_confirmation(message):
        session = repo.setdefault(session_id, {})
        session["resolved"] = True
        return "Que bom que pudemos ajudar. Caso precise, estamos à disposição!"

    # Fallback behaviour for non-resolution messages: simply echo them.
    return f"Recebido: {message}"