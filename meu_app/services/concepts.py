from __future__ import annotations

"""Banco de conceitos para expansão semântica baseada em taxonomias."""

from collections import defaultdict
from typing import Dict, Iterable, List, Set

class ConceptBank:
    """Estrutura simples que mapeia termos normalizados para tags canônicas."""

    def __init__(self, taxonomies: Iterable[Dict]) -> None:
        self.index: Dict[str, Set[str]] = defaultdict(set)
        self.tag_to_terms: Dict[str, Set[str]] = defaultdict(set)
        for tax in taxonomies:
            self._ingest("", tax)

    def _ingest(self, path: str, node: object) -> None:
        """Percorre recursivamente a taxonomia construindo os índices."""
        if isinstance(node, dict):
            for key, val in node.items():
                tag = f"{path}.{key}" if path else key
                self._ingest(tag, val)
        elif isinstance(node, list):
            for leaf in node:
                term = str(leaf).replace("_", " ").lower()
                self.index[term].add(path)
                self.tag_to_terms[path].add(term)

    def expand(self, frame: Dict[str, List[str]]) -> List[str]:
        """Retorna termos de busca expandidos com base no frame do caso."""
        seeds = set(map(str.lower, frame.get("institutos", []) + frame.get("palavras_chave", [])))
        tags: Set[str] = set()
        for s in seeds:
            for term, tgs in self.index.items():
                if s in term:
                    tags |= tgs
        qterms: List[str] = list(seeds)
        for tag in list(tags):
            qterms.extend(self.tag_to_terms[tag])
        # dedup preservando ordem
        seen: Set[str] = set()
        deduped = []
        for t in qterms:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        return deduped