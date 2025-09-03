from __future__ import annotations

"""Simple text classification utilities.

Currently exposes :func:`guess_tema` which mirrors the heuristic
implemented originally inside the PDF indexer service.  The goal of the
function is to perform a very lightweight topic detection without
requiring an external model.  It is intentionally conservative: if no
keywords are matched the function returns ``None``.
"""

from typing import Optional

# Mapping of topic -> list of keywords.  The lists were extracted from the
# heuristic used in ``pdf_indexer`` where small sets of Portuguese
# keywords were scanned in the text.
_TEMA_KEYWORDS = {
    "familia": ["divórcio", "guarda", "pensão", "casamento", "filho", "adoção"],
    "consumidor": ["produto", "loja", "garantia", "compra", "serviço", "consumidor"],
    "trabalhista": ["salário", "empregado", "empregador", "rescisão", "clt", "trabalhista"],
    "tributario": ["imposto", "tributo", "fiscal", "icms", "iptu", "ipva", "irpf", "irpj"],
    "penal": ["crime", "pena", "prisão", "delegacia", "polícia"],
    "previdenciario": ["inss", "aposentadoria", "benefício", "previdenciário"],
    "civil": ["indenização", "responsabilidade", "contrato", "dano moral", "cível"],
}


def guess_tema(texto: str) -> Optional[str]:
    """Guess a legal topic from a given piece of text.

    The implementation is intentionally lightweight and rule based.  The
    text is converted to lower case and scanned for keywords defined in
    ``_TEMA_KEYWORDS``.  The first matching topic is returned.  If no
    keywords are found, ``None`` is returned.

    Parameters
    ----------
    texto:
        Free form text where the topic should be identified.

    Returns
    -------
    Optional[str]
        The detected topic or ``None`` when no match is found.
    """

    if not texto:
        return None

    txt = texto.lower()
    for tema, keywords in _TEMA_KEYWORDS.items():
        if any(k in txt for k in keywords):
            return tema
    return None


class Classifier:
    """Small wrapper class exposing ``guess_tema`` as a method."""

    def guess_tema(self, texto: str) -> Optional[str]:
        return guess_tema(texto)

    def classify(self, texto: str):
        """Compatibility helper returning ``(intent, tema)``.

        Older callers expect a ``classify`` method returning both
        intent and topic.  The lightweight classifier only guesses the
        topic, so we return ``None`` for intent and the detected topic
        (or ``None``) for the second element.  This keeps backward
        compatibility without introducing heavier dependencies.
        """

        tema = guess_tema(texto)
        return None, tema