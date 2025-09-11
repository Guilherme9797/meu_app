from __future__ import annotations
from typing import Any, Dict, List, Tuple
import math
try:
    from .buscador_pdf import buscar_pdf  # type: ignore
except Exception:
    def buscar_pdf(qterms: List[str], topk: int = 6) -> List[Dict[str, Any]]:
        return []
try:
    from ..retrievers.datajud import datajud_search  # type: ignore
except Exception:
    def bnp_search(qterms: List[str], filters: Dict[str, Any], topk: int = 6) -> List[Dict[str, Any]]:
        return []
def build_filters_by_domain(dominios: List[str]) -> Dict[str, List[str]]:
    f: Dict[str, List[str]] = {"must_not": [], "prefer": []}
    if "trabalho" in dominios or "processual_trabalho" in dominios:
        f["prefer"] += ["TRT", "TST"]
        f["must_not"] += ["TJ Militar"]
    if "empresarial" in dominios:
        f["prefer"] += ["TJ", "STJ"]
        f["must_not"] += ["TRT"]
    if "penal" in dominios or "processual_penal" in dominios:
        f["prefer"] += ["TJ", "STJ", "STF"]
    if "previdenciário" in dominios:
        f["prefer"] += ["JF", "JEF", "TRF"]
    if "imobiliário" in dominios:
        f["prefer"] += ["TJ", "STJ"]
        f["must_not"] += ["TRT"]
    return f
def _cos(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _vectorize(llm: Any, text: str) -> List[float]:
    # usa o mesmo provedor de embeddings já usado no projeto
    em = llm.client.embeddings.create(model=getattr(llm, "embed_model", "text-embedding-3-small"), input=[text])
    return em.data[0].embedding  # type: ignore


def _mmr_diversify(llm: Any, query: str, hits: List[Dict[str, Any]], k: int = 12, lambda_: float = 0.7) -> List[Dict[str, Any]]:
    # precisa que cada hit tenha algum 'trecho'/'texto' — ajuste se o seu schema for diferente
    qv = _vectorize(llm, query)
    doc_vecs: List[Tuple[int, List[float]]] = []
    for i, h in enumerate(hits):
        txt = h.get("trecho") or h.get("texto") or h.get("resumo") or ""
        doc_vecs.append((i, _vectorize(llm, txt[:1500])))

    selected: List[int] = []
    while len(selected) < min(k, len(hits)):
        best = (-1, -1.0)
        for i, dv in doc_vecs:
            if i in selected:
                continue
            rel = _cos(qv, dv)
            if not selected:
                score = rel
            else:
                maxsim = max(_cos(dv, doc_vecs[j][1]) for j in selected)
                score = lambda_ * rel - (1 - lambda_) * maxsim
            if score > best[1]:
                best = (i, score)
        if best[0] == -1:
            break
        selected.append(best[0])
    return [hits[i] for i in selected]


def _dedup(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for h in hits:
        key = (h.get("fonte"), h.get("id"))
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out


def search_all(llm: Any, qterms: List[str], frame: Dict[str, Any], topk_each: int = 6, query_text: str = "") -> List[Dict[str, Any]]:
    filters = build_filters_by_domain(frame.get("dominios", []))
    faiss_hits = buscar_pdf(qterms, topk=topk_each)
    datajud_hits = datajud_search(qterms, filters, topk=topk_each)
    bnp_hits = bnp_search(qterms, filters, topk=topk_each)
    combo = _dedup(faiss_hits + datajud_hits + bnp_hits)
    # rerankeia e diversifica
    if query_text:
        combo = _mmr_diversify(llm, query_text, combo, k=12)
    else:
        combo = combo[:12]
    return combo