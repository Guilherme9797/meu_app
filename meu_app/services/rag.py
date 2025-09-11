from __future__ import annotations

"""Orquestra consultas a múltiplas fontes de conhecimento."""

from typing import Any, Dict, List

# Funções externas esperadas. Caso não estejam disponíveis, fornecemos stubs
try:  # pragma: no cover - dependências opcionais
    from .buscador_pdf import buscar_pdf  # type: ignore
except Exception:  # pragma: no cover
    def buscar_pdf(qterms: List[str], topk: int = 6) -> List[Dict[str, Any]]:  # type: ignore
        return []

try:  # pragma: no cover
    from ..retrievers.datajud import datajud_search  # type: ignore
except Exception:  # pragma: no cover
    def datajud_search(qterms: List[str], filters: Dict[str, Any], topk: int = 6) -> List[Dict[str, Any]]:  # type: ignore
        return []

try:  # pragma: no cover
    from ..providers.bnp_provider import bnp_search  # type: ignore
except Exception:  # pragma: no cover
    def bnp_search(qterms: List[str], filters: Dict[str, Any], topk: int = 6) -> List[Dict[str, Any]]:  # type: ignore
        return []


def rerank_and_diversify(*hit_lists: List[List[Dict[str, Any]]], k: int = 12) -> List[Dict[str, Any]]:
    """Combina resultados mantendo diversidade simples."""
    combo: List[Dict[str, Any]] = []
    for hits in hit_lists:
        combo.extend(hits)
    # corte simples; um reranker real aplicaria MMR
    return combo[:k]


def build_filters_by_domain(dominios: List[str]) -> Dict[str, List[str]]:
    """Regras de preferência/remoção de tribunais por domínio jurídico."""
    f: Dict[str, List[str]] = {"must_not": [], "prefer": []}
    if "trabalho" in dominios or "processual_trabalho" in dominios:
        f["prefer"] += ["TRT", "TST"]
        f["must_not"] += ["TJ Militar", "TRF penal único"]
    if "empresarial" in dominios:
        f["prefer"] += ["TJ", "STJ"]
        f["must_not"] += ["TRT"]
    if "penal" in dominios or "processual_penal" in dominios:
        f["prefer"] += ["TJ", "STJ", "STF"]
    if "previdenciário" in dominios:
        f["prefer"] += ["JF", "JEF", "TRF"]
    return f


def search_all(qterms: List[str], frame: Dict[str, Any], topk_each: int = 6) -> List[Dict[str, Any]]:
    """Busca em todas as fontes e retorna pacote de contexto diversificado."""
    filters = build_filters_by_domain(frame.get("dominios", []))
    faiss_hits = buscar_pdf(qterms, topk=topk_each)
    datajud_hits = datajud_search(qterms, filters, topk=topk_each)
    bnp_hits = bnp_search(qterms, filters, topk=topk_each)
    pack = rerank_and_diversify(faiss_hits, datajud_hits, bnp_hits, k=12)
    return pack