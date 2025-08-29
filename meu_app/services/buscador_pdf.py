from __future__ import annotations
import json
import os
import re
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable, Tuple
import numpy as np

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None

logger = logging.getLogger(__name__)

RE_PROC = re.compile(r"\b\d{7}\-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")
@dataclass
class RetrievedChunk:
    text: str
    score: float
    doc_id: str
    doc_title: str
    span: str
    path: str
class Retriever:
    """Retriever FAISS com pré-filtros por tema e processos."""
    def __init__(
        self,
        index_path: str,
        embed_fn: Callable[[str], np.ndarray],
        device: str = "cpu",
    ) -> None:
        self.index_dir = index_path
        self.embed_fn = embed_fn
        self.device = device
        self.faiss_index = None
        self.manifest: List[Dict[str, Any]] = []
        self._load_index()

    def retrieve(
        self,
        query: str,
        tema: Optional[str],
        ents: Dict[str, Any],
        k: int = 6,
    ) -> List[RetrievedChunk]:
        if not self.faiss_index or not self.manifest:
            logger.warning("Índice/manifest não carregados. Retornando vazio.")
            return []
        candidate_ids = self._prefilter_candidates(tema=tema, ents=ents)
        qvec = self._safe_embed(query)
        if qvec is None:
            return []
        ids, scores = self._search_restrict(qvec, candidate_ids=candidate_ids, top_k=max(k * 5, k))
        if not ids:
            return []
        chunks = self._build_chunks(ids, scores, qvec, top_k=k)
        return chunks

    def _load_index(self) -> None:
        idx_path = os.path.join(self.index_dir, "index.faiss")
        man_path = os.path.join(self.index_dir, "manifest.json")
        if not os.path.exists(idx_path) or not os.path.exists(man_path):
            logger.error("Arquivos do índice ausentes: %s | %s", idx_path, man_path)
            return
        if faiss is None:
            logger.error("FAISS não está instalado. `pip install faiss-cpu` (ou faiss-gpu).")
            return
        self.faiss_index = faiss.read_index(idx_path)
        with open(man_path, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)
        if hasattr(self.faiss_index, "ntotal"):
            n_idx = int(self.faiss_index.ntotal)  # type: ignore[attr-defined]
        else:
            n_idx = len(self.manifest)
        if n_idx != len(self.manifest):
            logger.warning("Tamanho do índice (%d) difere do manifest (%d).", n_idx, len(self.manifest))
        logger.info("FAISS carregado (%d vetores). Manifest com %d chunks.", n_idx, len(self.manifest))

    def _safe_embed(self, text: str) -> Optional[np.ndarray]:
        try:
            vec = self.embed_fn(text)
            if not isinstance(vec, np.ndarray):
                vec = np.array(vec, dtype="float32")
            vec = vec.astype("float32")
            if vec.ndim == 1:
                vec = vec.reshape(1, -1)
            return vec
        except Exception as e:
            logger.exception("Falha ao gerar embedding: %s", e)
            return None

    def _prefilter_candidates(self, tema: Optional[str], ents: Dict[str, Any]) -> Optional[np.ndarray]:
        n = len(self.manifest)
        mask = np.ones(n, dtype=bool)
        if tema and tema != "geral":
            temas = np.array([(c.get("tema") or "").lower() for c in self.manifest])
            mask &= (temas == tema.lower())
        processos_ents = ents.get("processos") or []
        processos_ents = list({p.strip() for p in processos_ents if isinstance(p, str) and p.strip()})
        if processos_ents:
            def has_proc(cmeta: Dict[str, Any]) -> bool:
                procs_meta = cmeta.get("processos") or []
                if procs_meta and isinstance(procs_meta, list):
                    st_meta = set(map(str, procs_meta))
                    for p in processos_ents:
                        if p in st_meta:
                            return True
                ft = cmeta.get("fulltext")
                if isinstance(ft, str) and ft:
                    for p in processos_ents:
                        if p in ft:
                            return True
                return False
            proc_mask = np.array([has_proc(c) for c in self.manifest], dtype=bool)
            mask &= proc_mask
        idxs = np.nonzero(mask)[0]
        if idxs.size == 0:
            if processos_ents and (tema and tema != "geral"):
                idxs = np.nonzero(np.array([(c.get("tema") or "").lower() for c in self.manifest]) == (tema or "").lower())[0]
            if idxs.size == 0 and (tema and tema != "geral"):
                idxs = np.nonzero(np.array([(c.get("tema") or "").lower() for c in self.manifest]) == (tema or "").lower())[0]
            if idxs.size == 0:
                return None
        return idxs.astype("int64")

    def _search_restrict(self, qvec: np.ndarray, candidate_ids: Optional[np.ndarray], top_k: int) -> Tuple[List[int], List[float]]:
        if self.faiss_index is None:
            return [], []
        index = self.faiss_index
        try:
            D, I = index.search(qvec, top_k * 10)
            I = I[0].tolist()
            D = D[0].tolist()
        except Exception as e:
            logger.exception("Falha ao consultar FAISS: %s", e)
            return [], []
        ids_scores = list(zip(I, D))
        ids_scores = [(i, s) if i >= 0 else None for i, s in ids_scores]
        ids_scores = [x for x in ids_scores if x is not None]
        if candidate_ids is not None:
            cand_set = set(map(int, candidate_ids.tolist()))
            ids_scores = [(i, s) for (i, s) in ids_scores if i in cand_set]
        ids_scores = ids_scores[:top_k]
        if not ids_scores:
            return [], []
        ids, scores = zip(*ids_scores)
        return list(ids), list(scores)

    def _build_chunks(self, ids: List[int], scores: List[float], qvec: np.ndarray, top_k: int) -> List[RetrievedChunk]:
        items: List[Tuple[int, float, Dict[str, Any]]] = []
        for idx, raw_score in zip(ids, scores):
            meta = self._safe_manifest(idx)
            if not meta:
                continue
            items.append((idx, float(raw_score), meta))
        items.sort(key=lambda t: t[1], reverse=True)
        items = items[:top_k]
        out: List[RetrievedChunk] = []
        for _, sc, meta in items:
            out.append(
                RetrievedChunk(
                    text=meta.get("text") or meta.get("fulltext") or "",
                    score=float(sc),
                    doc_id=str(meta.get("doc_id") or ""),
                    doc_title=str(meta.get("doc_title") or ""),
                    span=str(meta.get("span") or ""),
                    path=str(meta.get("path") or ""),
                )
            )
        return out

    def _safe_manifest(self, idx: int) -> Optional[Dict[str, Any]]:
        try:
            return self.manifest[idx]
        except Exception:
            return None
__all__ = ["Retriever", "RetrievedChunk"]