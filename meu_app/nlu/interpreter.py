from __future__ import annotations

"""Simplified universal interpreter for legal intents.

This module provides a light-weight natural language interpreter that extracts
basic structured information from a user's question. The implementation is
heuristic but designed to be dependency free so it can run in the test
environment.
"""

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Tuple
import json
import os
import re
import unicodedata

from ..services.patterns import load_rules_from_taxonomy_dir, PatternRule

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Normalize text by lowercasing, removing accents and collapsing spaces."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> List[str]:
    """Very small tokenizer that keeps only alphanumeric tokens."""
    return re.findall(r"\w+", normalize_text(text))


# Minimal stop word list for Portuguese (can be expanded as needed).
PT_STOPWORDS = {
    "a",
    "o",
    "e",
    "de",
    "do",
    "da",
    "para",
    "com",
    "que",
    "quando",
    "como",
    "porque",
    "por",
    "no",
    "na",
    "em",
}

# Tokens indicating urgency.
URGENCY_TOKENS = {"urgencia", "urgente", "liminar", "imediato", "imediata"}

# Very small mapping of platform hints.
PLATFORM_HINTS: Dict[str, List[str]] = {
    "instagram": ["instagram", "insta"],
    "facebook": ["facebook", "fb"],
    "whatsapp": ["whatsapp", "zap", "whats"],
    "youtube": ["youtube", "yt"],
    "tiktok": ["tiktok", "tik tok"],
}


# ---------------------------------------------------------------------------
# Light weight pattern scorer
# ---------------------------------------------------------------------------

class SimplePatternScorer:
    """Scores text against pattern rules loaded from a directory."""

    def __init__(self, pattern_dir: str):
        self.rules: List[PatternRule] = load_rules_from_taxonomy_dir(pattern_dir)

    def score(self, text: str, top_k: int = 50) -> Tuple[List[str], List[str]]:
        if not text or not self.rules:
            return [], []
        norm = normalize_text(text)
        hits: List[PatternRule] = []
        for rule in self.rules:
            any_hit = any(normalize_text(tok) in norm for tok in rule.any_of)
            none_hit = any(normalize_text(tok) in norm for tok in rule.none_of)
            if any_hit and not none_hit:
                hits.append(rule)
        topics = [r.name for r in hits[:top_k]]
        dominios: List[str] = []
        for r in hits:
            for d in r.dominios:
                if d not in dominios:
                    dominios.append(d)
        return topics, dominios


# ---------------------------------------------------------------------------
# Entity and request extraction helpers
# ---------------------------------------------------------------------------

def extract_entities(text: str) -> Tuple[List[str], List[str]]:
    """Extract very small set of entities and deadlines from text."""
    entities: List[str] = []
    deadlines: List[str] = []

    # emails
    entities.extend(re.findall(r"[\w.\-]+@[\w.\-]+", text))
    # dates like 10/10/2023 or 10/10
    deadlines.extend(re.findall(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", text))
    return entities, deadlines


def extract_requests(text: str, topics: List[str]) -> List[str]:
    """Heuristically extract request phrases from text."""
    reqs: List[str] = []
    pattern = re.compile(r"(?:quero|gostaria|solicito|peco|desejo) ([^\.\n!?]+)", re.IGNORECASE)
    for match in pattern.findall(text):
        req = match.strip()
        if req:
            reqs.append(req)
    return reqs


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class LegalIntent:
    original_text: str
    language: str
    domains: List[str]
    topics: List[str]
    keywords: List[str]
    entities: List[str]
    requests: List[str]
    deadlines: List[str]
    urgency: bool
    platforms: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Universal Interpreter
# ---------------------------------------------------------------------------

class UniversalInterpreter:
    def __init__(self, pattern_dir: str = ""):
        self.scorer = SimplePatternScorer(pattern_dir)

    # ----- detectors -----
    def detect_language(self, text: str) -> str:
        t = normalize_text(text)
        if re.search(r"\b(o|a|de|do|da|para|com|sem|que|quando|como|porque)\b", t):
            return "pt-BR"
        return "unknown"

    def detect_platforms(self, text: str) -> List[str]:
        plats: List[str] = []
        lowered = normalize_text(text)
        for plat, hints in PLATFORM_HINTS.items():
            for h in hints:
                if f" {normalize_text(h)} " in f" {lowered} ":
                    plats.append(plat)
                    break
        return sorted(set(plats))

    # ----- main API -----
    def interpret(self, text: str) -> LegalIntent:
        lang = self.detect_language(text)
        entities, deadlines = extract_entities(text)
        top_topics, domains = self.scorer.score(text, top_k=50)

        toks = [t for t in tokenize(text) if t not in PT_STOPWORDS]
        seen: set[str] = set()
        keywords: List[str] = []
        for t in toks:
            if t not in seen:
                keywords.append(t)
                seen.add(t)
                if len(keywords) >= 20:
                    break

        requests = extract_requests(text, top_topics)
        urgency = any(re.search(fr"\b{kw}\b", normalize_text(text)) for kw in URGENCY_TOKENS)
        platforms = self.detect_platforms(text)

        return LegalIntent(
            original_text=text,
            language=lang,
            domains=domains,
            topics=top_topics,
            keywords=keywords,
            entities=entities,
            requests=requests,
            deadlines=deadlines,
            urgency=urgency,
            platforms=platforms,
        )


# ---------------------------------------------------------------------------
# Manual execution helper for quick debugging
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pattern_dir = os.environ.get("PATTERN_DIR", "meu_app/patternrules")
    ui = UniversalInterpreter(pattern_dir=pattern_dir)
    sample = (
        "Divulgaram uma foto minha no Instagram me chamando de caloteiro. "
        "Quero remover o conteúdo e pedir indenização por danos morais com urgência."
    )
    intent = ui.interpret(sample)
    print(json.dumps(intent.to_dict(), ensure_ascii=False, indent=2))