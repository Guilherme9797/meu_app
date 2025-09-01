from __future__ import annotations

"""Utilities for extracting structured information from free text."""

import re
from typing import Iterable, List

# Regular expression for Brazilian CNJ process numbers.  It accepts both the
# fully formatted form ("0000000-00.0000.0.00.0000") and a compact version
# with only digits.  Matches are normalised to the canonical format.
_PROCESS_RE = re.compile(
    r"\b(?:\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}|\d{20})\b"
)


def _normalize(number: str) -> str:
    """Normalize a process number to the canonical CNJ format."""

    digits = re.sub(r"\D", "", number)
    if len(digits) != 20:
        return number
    return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:]}"


def extract_process_numbers(texto: str) -> List[str]:
    """Extract CNJ process numbers from *texto*.

    Parameters
    ----------
    texto:
        Free-form text that may contain process numbers.

    Returns
    -------
    List[str]
        List of numbers normalised to the standard CNJ format.
    """

    if not texto:
        return []
    matches = _PROCESS_RE.findall(texto)
    return [_normalize(m) for m in matches]


class Extractor:
    """Simple wrapper exposing :func:`extract_process_numbers`."""

    def extract_process_numbers(self, texto: str) -> List[str]:
        return extract_process_numbers(texto)