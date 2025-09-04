# -*- coding: utf-8 -*-
from __future__ import annotations
import os, re, json, logging, unicodedata
from typing import Any, Dict, List, Optional

try:
    import httpx
except Exception:
    httpx = None

class Chunk:
    def __init__(self, text: str, source: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        self.text = text
        self.source = source or "datajud"
        self.metadata = metadata or {}

DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"
ALIASES = {
    "TST":  f"{DATAJUD_BASE}/api_publica_tst/_search",
    "TSE":  f"{DATAJUD_BASE}/api_publica_tse/_search",
    "STJ":  f"{DATAJUD_BASE}/api_publica_stj/_search",
    "STM":  f"{DATAJUD_BASE}/api_publica_stm/_search",
    "TRF1": f"{DATAJUD_BASE}/api_publica_trf1/_search",
    "TRF2": f"{DATAJUD_BASE}/api_publica_trf2/_search",
    "TRF3": f"{DATAJUD_BASE}/api_publica_trf3/_search",
    "TRF4": f"{DATAJUD_BASE}/api_publica_trf4/_search",
    "TRF5": f"{DATAJUD_BASE}/api_publica_trf5/_search",
    "TRF6": f"{DATAJUD_BASE}/api_publica_trf6/_search",
    "TJSP": f"{DATAJUD_BASE}/api_publica_tjsp/_search",
    "TJRJ": f"{DATAJUD_BASE}/api_publica_tjrj/_search",
    "TJMG": f"{DATAJUD_BASE}/api_publica_tjmg/_search",
    "TJRS": f"{DATAJUD_BASE}/api_publica_tjrs/_search",
    "TJBA": f"{DATAJUD_BASE}/api_publica_tjba/_search",
    "TJPR": f"{DATAJUD_BASE}/api_publica_tjpr/_search",
    "TJSC": f"{DATAJUD_BASE}/api_publica_tjsc/_search",
    "TJDFT":f"{DATAJUD_BASE}/api_publica_tjdft/_search",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()

_CNJ_RE_FMT = re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")
_CNJ_RE_NUM = re.compile(r"\b\d{20}\b")


def _pick_aliases(user_text: str) -> List[str]:
    env = (os.getenv("DATAJUD_ALIASES") or "").strip()
    if env:
        al = [a.strip().upper() for a in env.split(",") if a.strip()]
        return [a for a in al if a in ALIASES]
    t = _norm(user_text)
    picks: List[str] = []
    for key in ["STJ","TJSP","TJRJ","TJMG","TJRS","TRF1","TRF3","TRF4","TJDFT","TJPR","TJSC","TJBA"]:
        if key.lower() in t:
            picks.append(key)
    if picks:
        return [p for p in picks if p in ALIASES]
    return ["TJSP","TJRJ","TJMG","TRF1","TRF3","TRF4","TJDFT"]


def _extract_cnj(user_text: str) -> Optional[str]:
    t = user_text or ""
    m1 = _CNJ_RE_FMT.search(t)
    if m1:
        return re.sub(r"\D", "", m1.group(0))
    m2 = _CNJ_RE_NUM.search(t)
    if m2:
        return m2.group(0)
    return None


def _http_client(timeout: float = 20.0):
    if httpx is None:
        raise RuntimeError("httpx não disponível neste ambiente.")
    return httpx.Client(timeout=timeout)


class DatajudClient:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("DATAJUD_API_KEY") or \
            "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
        self.headers = {
            "Authorization": f"APIKey {self.api_key}",
            "Content-Type": "application/json",
        }

    def search(self, alias: str, body: Dict[str, Any]) -> Dict[str, Any]:
        url = ALIASES[alias]
        with _http_client() as cli:
            r = cli.post(url, headers=self.headers, content=json.dumps(body))
            r.raise_for_status()
            return r.json()


class DatajudRetriever:
    def __init__(self, client: Optional[DatajudClient] = None, size: int = 10) -> None:
        self.client = client or DatajudClient()
        self.size = max(1, min(int(size), 1000))

    def _build_body(self, user_text: str, size: int, search_after: Optional[List[Any]] = None) -> Dict[str, Any]:
        cnj = _extract_cnj(user_text)
        if cnj:
            return {"query": {"match": {"numeroProcesso": cnj}}, "size": size}
        body: Dict[str, Any] = {
            "size": size,
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": user_text,
                                "fields": [
                                    "classe.nome^3",
                                    "assuntos.nome^4",
                                    "movimentos.nome^2",
                                    "orgaoJulgador.nome",
                                ],
                                "type": "best_fields",
                                "operator": "or",
                            }
                        }
                    ],
                    "minimum_should_match": 1,
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}],
        }
        if search_after:
            body["search_after"] = search_after
        return body

    def _hit_to_chunk(self, hit: Dict[str, Any], alias: str) -> Chunk:
        src = hit.get("_source", {})
        numero = src.get("numeroProcesso")
        trib = src.get("tribunal")
        classe = (src.get("classe") or {}).get("nome")
        grau = src.get("grau")
        orgao = (src.get("orgaoJulgador") or {}).get("nome")
        assuntos = []
        for a in (src.get("assuntos") or []):
            if isinstance(a, dict):
                assuntos.append(a.get("nome"))
            elif isinstance(a, list) and a and isinstance(a[0], dict):
                assuntos.append(a[0].get("nome"))
        assuntos = [x for x in assuntos if x]
        movs = src.get("movimentos") or []
        top_movs = []
        for m in movs[-3:]:
            top_movs.append(f"{m.get('nome')} ({m.get('dataHora')})")
        resumo = []
        if classe:
            resumo.append(f"Classe: {classe}")
        if assuntos:
            resumo.append("Assuntos: " + ", ".join(assuntos[:4]))
        if top_movs:
            resumo.append("Movimentos: " + " | ".join(top_movs))
        text = (
            f"Processo {numero} – {trib}/{grau} – Órgão: {orgao or 'n/d'}.\n"
            + (". ".join(resumo) if resumo else "Metadados disponíveis.")
        )
        meta = {
            "tribunal": trib,
            "grau": grau,
            "orgaoJulgador": orgao,
            "classe": classe,
            "assuntos": assuntos,
            "numeroProcesso": numero,
            "_id": hit.get("_id"),
            "_index": hit.get("_index"),
        }
        return Chunk(text=text, source=f"datajud:{alias}", metadata=meta)

    def retrieve(self, query: str, k: int = 6) -> List[Chunk]:
        aliases = _pick_aliases(query)
        out: List[Chunk] = []
        for alias in aliases:
            try:
                body = self._build_body(query, size=min(self.size, k))
                resp = self.client.search(alias, body)
                hits = (((resp or {}).get("hits") or {}).get("hits") or [])
                for h in hits[:k]:
                    out.append(self._hit_to_chunk(h, alias=alias))
            except Exception:
                logging.exception("Datajud falhou em %s", alias)
                continue
        return out


class CombinedRetriever:
    def __init__(self, retrievers: List[Any], max_per_source: int = 6, chunk_max_chars: int = 450) -> None:
        self.retrievers = retrievers
        self.max_per_source = max_per_source
        self.chunk_max_chars = chunk_max_chars

    def retrieve(self, query: str, k: int = 6) -> List[Chunk]:
        pool: List[Chunk] = []
        for r in self.retrievers:
            try:
                if hasattr(r, "retrieve"):
                    items = r.retrieve(query, k=min(self.max_per_source, k)) or []
                elif hasattr(r, "buscar_contexto"):
                    ctx = r.buscar_contexto(query, k=min(self.max_per_source, k)) or ""
                    items = [Chunk(ctx[:self.chunk_max_chars], source="pdf_ctx")]
                else:
                    items = []
                for it in items:
                    txt = getattr(it, "text", "") or ""
                    if len(txt) > self.chunk_max_chars:
                        txt = txt[:self.chunk_max_chars]
                    pool.append(
                        Chunk(txt, source=getattr(it, "source", None), metadata=getattr(it, "metadata", None))
                    )
            except Exception:
                logging.exception("CombinedRetriever: falha em %s", type(r).__name__)
                continue
        seen = set()
        deduped: List[Chunk] = []
        for c in pool:
            key = (c.text or "").strip()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)
            if len(deduped) >= k:
                break
        return deduped