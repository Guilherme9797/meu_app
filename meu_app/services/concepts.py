from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Set
import unicodedata


def _norm(s: str) -> str:
    s = s.replace("_", " ").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.split())

class ConceptBank:
    def __init__(self, taxonomies: Iterable[Dict]) -> None:
        self.index: Dict[str, Set[str]] = defaultdict(set)       # termo -> tags
        self.tag_to_terms: Dict[str, Set[str]] = defaultdict(set) # tag -> termos
        for tax in taxonomies:
            self._ingest("", tax)

    def _ingest(self, path: str, node: object) -> None:
        if isinstance(node, dict):
            for key, val in node.items():
                tag = f"{path}.{key}" if path else key
                self._ingest(tag, val)
        elif isinstance(node, list):
            for leaf in node:
                term = _norm(str(leaf))
                self.index[term].add(path)
                self.tag_to_terms[path].add(term)
    
    def expand(self, frame: Dict[str, List[str]], pergunta: str | None = None) -> List[str]:
        seeds = set(_norm(s) for s in (frame.get("institutos", []) + frame.get("palavras_chave", [])))
        # fuzzy: sobreposição de tokens
        tags: Set[str] = set()
        for s in seeds:
            stoks = set(s.split())
            for term, tgs in self.index.items():
                ttoks = set(term.split())
                if s in term or term in s or len(stoks & ttoks) >= max(1, min(len(stoks), len(ttoks)) - 1):
                    tags |= tgs

        qterms: List[str] = list(seeds)
        for tag in list(tags):
            qterms.extend(list(self.tag_to_terms[tag]))

        # fallback: n-grams da pergunta
        if pergunta:
            pq = _norm(pergunta)
            toks = pq.split()
            for n in (3, 2):
                for i in range(len(toks) - n + 1):
                    qterms.append(" ".join(toks[i : i + n]))

        # dedup preservando ordem
        seen: Set[str] = set()
        deduped = []
        for t in qterms:
            if t and t not in seen:
                seen.add(t)
                deduped.append(t)
        return deduped[:60]
