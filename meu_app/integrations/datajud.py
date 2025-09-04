# -*- coding: utf-8 -*-
"""
Integração Datajud – API Pública CNJ
- Cliente HTTP com rate limiting (<=120 req/min)
- DatajudRetriever que expõe .retrieve(query, k) -> List[Chunk-like]
- CombinedRetriever para unir PDF + Datajud sob uma interface única

Requisitos de uso e limites (conforme Termo de Uso do CNJ):
- Header: Authorization: APIKey <SUA_CHAVE>
- Finalidade legal e não comercial; sem coleta/armazenamento de dados pessoais;
- CNJ não garante precisão/atualidade; limite <=120 req/min (compliance abaixo).
"""
from __future__ import annotations
import re
import time
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import httpx
except Exception as _e:
    httpx = None  # impedirá uso e logará erro

# ------------------------------
# Util: Token bucket simples
# ------------------------------
class _TokenBucket:
    def __init__(self, rate_per_sec: float, capacity: int):
        self.rate = float(rate_per_sec)
        self.capacity = int(capacity)
        self.tokens = float(capacity)
        self.ts = time.monotonic()

    def consume(self, amount: float = 1.0) -> None:
        now = time.monotonic()
        elapsed = now - self.ts
        self.ts = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        if self.tokens < amount:
            # dormir o mínimo para 1 “token”
            need = amount - self.tokens
            wait = need / self.rate if self.rate > 0 else 0.0
            time.sleep(max(0.0, wait))
            self.ts = time.monotonic()
            # após dormir, temos ao menos 'amount'
            self.tokens = max(0.0, self.tokens + wait * self.rate)
        self.tokens -= amount


# ------------------------------
# Mapeamento de endpoints
# ------------------------------
DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"
ALIASES = {
    # Tribunais Superiores
    "tst":  "/api_publica_tst/_search",
    "tse":  "/api_publica_tse/_search",
    "stj":  "/api_publica_stj/_search",
    "stm":  "/api_publica_stm/_search",
    # Justiça Federal
    "trf1": "/api_publica_trf1/_search",
    "trf2": "/api_publica_trf2/_search",
    "trf3": "/api_publica_trf3/_search",
    "trf4": "/api_publica_trf4/_search",
    "trf5": "/api_publica_trf5/_search",
    "trf6": "/api_publica_trf6/_search",
    # Justiça Estadual
    "tjac": "/api_publica_tjac/_search",
    "tjal": "/api_publica_tjal/_search",
    "tjam": "/api_publica_tjam/_search",
    "tjap": "/api_publica_tjap/_search",
    "tjba": "/api_publica_tjba/_search",
    "tjce": "/api_publica_tjce/_search",
    "tjdft":"/api_publica_tjdft/_search",
    "tjes": "/api_publica_tjes/_search",
    "tjgo": "/api_publica_tjgo/_search",
    "tjma": "/api_publica_tjma/_search",
    "tjmg": "/api_publica_tjmg/_search",
    "tjms": "/api_publica_tjms/_search",
    "tjmt": "/api_publica_tjmt/_search",
    "tjpa": "/api_publica_tjpa/_search",
    "tjpb": "/api_publica_tjpb/_search",
    "tjpe": "/api_publica_tjpe/_search",
    "tjpi": "/api_publica_tjpi/_search",
    "tjpr": "/api_publica_tjpr/_search",
    "tjrj": "/api_publica_tjrj/_search",
    "tjrn": "/api_publica_tjrn/_search",
    "tjro": "/api_publica_tjro/_search",
    "tjrr": "/api_publica_tjrr/_search",
    "tjrs": "/api_publica_tjrs/_search",
    "tjsc": "/api_publica_tjsc/_search",
    "tjse": "/api_publica_tjse/_search",
    "tjsp": "/api_publica_tjsp/_search",
    "tjto": "/api_publica_tjto/_search",
    # Justiça Eleitoral
    "tre-ac": "/api_publica_tre-ac/_search",
    "tre-al": "/api_publica_tre-al/_search",
    "tre-am": "/api_publica_tre-am/_search",
    "tre-ap": "/api_publica_tre-ap/_search",
    "tre-ba": "/api_publica_tre-ba/_search",
    "tre-ce": "/api_publica_tre-ce/_search",
    "tre-dft":"/api_publica_tre-dft/_search",
    "tre-es": "/api_publica_tre-es/_search",
    "tre-go": "/api_publica_tre-go/_search",
    "tre-ma": "/api_publica_tre-ma/_search",
    "tre-mg": "/api_publica_tre-mg/_search",
    "tre-ms": "/api_publica_tre-ms/_search",
    "tre-mt": "/api_publica_tre-mt/_search",
    "tre-pa": "/api_publica_tre-pa/_search",
    "tre-pb": "/api_publica_tre-pb/_search",
    "tre-pe": "/api_publica_tre-pe/_search",
    "tre-pi": "/api_publica_tre-pi/_search",
    "tre-pr": "/api_publica_tre-pr/_search",
    "tre-rj": "/api_publica_tre-rj/_search",
    "tre-rn": "/api_publica_tre-rn/_search",
    "tre-ro": "/api_publica_tre-ro/_search",
    "tre-rr": "/api_publica_tre-rr/_search",
    "tre-rs": "/api_publica_tre-rs/_search",
    "tre-sc": "/api_publica_tre-sc/_search",
    "tre-se": "/api_publica_tre-se/_search",
    "tre-sp": "/api_publica_tre-sp/_search",
    "tre-to": "/api_publica_tre-to/_search",
    # Justiça Militar Estadual
    "tjmmg": "/api_publica_tjmmg/_search",
    "tjmrs": "/api_publica_tjmrs/_search",
    "tjmsp": "/api_publica_tjmsp/_search",
}

# ordem “mais prováveis” (para evitar varrer tudo quando tribunal não informado)
PREFERRED_ORDER = [
    # estaduais mais demandados + TRFs + superiores
    "tjsp","tjrj","tjmg","tjrs","tjba","tjpr","tjsc","tjpe","tjce","tjdft",
    "trf1","trf2","trf3","trf4","trf5","trf6",
    "stj","tst","tse","stm",
]


# ------------------------------
# Cliente HTTP
# ------------------------------
@dataclass
class DatajudClient:
    api_key: str
    timeout: float = 20.0
    max_per_minute: int = 120

    def __post_init__(self):
        self._rate = _TokenBucket(rate_per_sec=self.max_per_minute/60.0, capacity=self.max_per_minute)
        if httpx is None:
            logging.error("httpx não disponível; DatajudClient ficará inoperante.")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"APIKey {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "meu_app/1.0 (Datajud integration)",
        }

    def _post(self, path: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if httpx is None:
            return None
        self._rate.consume(1.0)
        url = f"{DATAJUD_BASE}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, headers=self._headers(), json=body)
                if resp.status_code >= 400:
                    logging.warning("Datajud %s -> %s: %s", path, resp.status_code, resp.text[:300])
                    return None
                return resp.json()
        except Exception:
            logging.exception("Falha no POST Datajud %s", path)
            return None

    def search(self, alias: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        path = ALIASES.get(alias.lower().strip())
        if not path:
            logging.debug("Alias Datajud inválido: %s", alias)
            return None
        return self._post(path, body)


# ------------------------------
# Heurísticas de entrada
# ------------------------------
_CLEAN_NUM = re.compile(r"\D+")

def extract_cnj_numbers(text: str) -> List[str]:
    """
    Extrai números CNJ (20 dígitos) do texto, aceitando formatado (NNNNNNN-DD.AAAA.J.TR.OOOO)
    ou em qualquer mistura com pontuação. Retorna lista de strings com 20 dígitos.
    """
    if not text:
        return []
    # pega qualquer sequência de >= 20 dígitos ao remover pontuação
    raw = _CLEAN_NUM.sub("", text)
    found = []
    for i in range(0, max(0, len(raw) - 19)):
        s = raw[i:i+20]
        if len(s) == 20 and s.isdigit():
            found.append(s)
    # também tentar regex formatado clássico
    rx = re.compile(r"\b(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})\b")
    for m in rx.finditer(text or ""):
        s = "".join(m.groups())
        if len(s) == 20:
            found.append(s)
    # uniq preservando ordem
    out, seen = [], set()
    for s in found:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

def guess_aliases(text: str) -> List[str]:
    """
    Detecta siglas de tribunais no texto (ex.: TJSP, TRF1, STJ...).
    Se não houver, devolve ordem preferida (subset) para tentativa.
    """
    t = (text or "").upper()
    hits = []
    # Diretos
    for sigla in [
        "TJSP","TJRJ","TJMG","TJRS","TJBA","TJPR","TJSC","TJPE","TJCE","TJDFT","TJGO",
        "TRF1","TRF2","TRF3","TRF4","TRF5","TRF6",
        "STJ","TST","TSE","STM",
        "TJMS","TJMT","TJPA","TJPB","TJPI","TJRN","TJRO","TJRR","TJTO","TJES","TJMA","TJAP","TJAL","TJAM","TJAC"
    ]:
        if sigla in t:
            key = sigla.lower()
            # mapeia "tjdf"->tjdft
            key = "tjdft" if key == "tjdf" else key
            if key in ALIASES:
                hits.append(key)
    if hits:
        # remove duplicados preservando ordem
        seen = set()
        out = []
        for h in hits:
            if h not in seen:
                out.append(h); seen.add(h)
        return out
    return list(PREFERRED_ORDER)


# ------------------------------
# Chunk helper (compatível com seu SERVICE)
# ------------------------------
class _Chunk:
    def __init__(self, text: str, source: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        self.text = text
        self.source = source
        self.metadata = metadata or {}


# ------------------------------
# Retriever do Datajud
# ------------------------------
@dataclass
class DatajudRetriever:
    client: DatajudClient
    page_size: int = 10

    def _make_body_numero(self, numero: str) -> Dict[str, Any]:
        return {
            "size": min(self.page_size, 50),
            "query": {"match": {"numeroProcesso": numero}},
            "sort": [{"@timestamp": {"order": "asc"}}],
        }

    def _query_once(self, alias: str, body: Dict[str, Any]) -> List[_Chunk]:
        data = self.client.search(alias, body)
        if not data or not isinstance(data, dict):
            return []
        hits = (data.get("hits") or {}).get("hits") or []
        out: List[_Chunk] = []
        for h in hits[: self.page_size]:
            src = h.get("_source", {})
            txt = self._render_source(src)
            out.append(_Chunk(txt, source=f"datajud:{alias}", metadata={"alias": alias, "id": h.get("_id")}))
        return out

    def _render_source(self, src: Dict[str, Any]) -> str:
        """Transforma um documento do Datajud em texto 'citável' no SOURCE PACK."""
        numero = src.get("numeroProcesso", "")
        trib = src.get("tribunal", "")
        grau = src.get("grau", "")
        cls  = (src.get("classe") or {}).get("nome", "")
        org  = (src.get("orgaoJulgador") or {}).get("nome", "")
        aju  = src.get("dataAjuizamento", "")
        assuntos = []
        for item in (src.get("assuntos") or []):
            # alguns TJs devolvem em lista de listas
            if isinstance(item, list):
                for it in item:
                    nm = (it or {}).get("nome")
                    if nm: assuntos.append(nm)
            else:
                nm = (item or {}).get("nome"); 
                if nm: assuntos.append(nm)
        assuntos = list(dict.fromkeys(assuntos))[:5]

        movs = src.get("movimentos") or []
        # pega os 3 últimos pelo campo dataHora (se vier)
        def _key(m): 
            return (m or {}).get("dataHora") or ""
        movs_sorted = sorted(movs, key=_key, reverse=True)[:3]
        mov_lines = []
        for m in movs_sorted:
            nome = (m or {}).get("nome", "")
            dh   = (m or {}).get("dataHora", "")
            mov_lines.append(f"- {nome} ({dh})" if nome else f"- {dh}")

        lines = []
        lines.append(f"Processo {numero} – {trib} – Grau {grau}")
        if cls: lines.append(f"Classe: {cls}")
        if org: lines.append(f"Órgão julgador: {org}")
        if aju: lines.append(f"Ajuizamento: {aju}")
        if assuntos: lines.append("Assuntos: " + ", ".join(assuntos))
        if mov_lines: 
            lines.append("Últimos movimentos:")
            lines.extend(mov_lines)
        return "\n".join(lines)

    # Interface pública
    def retrieve(self, query: str, k: int = 6) -> List[_Chunk]:
        """
        Estratégia:
        - Se houver número CNJ -> buscar por numeroProcesso em aliases prováveis (para na 1ª página com hit).
        - Se NÃO houver número, só tenta Datajud se o texto mencionar processo/tribunal (senão retorna []).
        """
        q = (query or "").strip()
        if not q:
            return []
        numeros = extract_cnj_numbers(q)
        aliases = guess_aliases(q)
        out: List[_Chunk] = []

        if numeros:
            for num in numeros[:2]:  # não exagerar por requisição
                body = self._make_body_numero(num)
                # tenta nas aliases candidatas até encontrar algo
                for al in aliases:
                    items = self._query_once(al, body)
                    if items:
                        out.extend(items)
                        break  # achou no 1º tribunal — suficiente p/ RAG
                if len(out) >= k:
                    break
            return out[:k]

        # sem número: heurística fraca — só tenta se parece “pesquisa processual”
        lower = q.lower()
        gatilhos = ("processo", "número", "numero", "vara", "tribunal", "comarca", "orgao julgador", "órgão julgador")
        if not any(g in lower for g in gatilhos):
            return []

        # exemplo frugal: procura por classe.nome aproximando por texto (match)
        # (atenção: isso pode trazer muito ruído; manter k pequeno)
        body = {
            "size": min(self.page_size, 10),
            "query": {"match": {"classe.nome": q}},
            "sort": [{"@timestamp": {"order": "asc"}}],
        }
        for al in aliases[:5]:
            items = self._query_once(al, body)
            out.extend(items)
            if len(out) >= k:
                break
        return out[:k]


# ------------------------------
# Combined retriever
# ------------------------------
class CombinedRetriever:
    """
    Unifica N retrievers sob .retrieve(query, k).
    Cada retriever pode expor .retrieve ou .buscar_contexto (string) que será “chunkado”.
    """
    def __init__(self, retrievers: Iterable[Any], chunk_max_chars: int = 450):
        self.retrievers = list(retrievers)
        self.chunk_max_chars = int(chunk_max_chars)

    def _split_ctx(self, ctx: str, max_chars: int = 450, max_chunks: int = 6) -> List[_Chunk]:
        if not ctx:
            return []
        parts = re.split(r"\n{2,}", ctx) or [ctx]
        out: List[_Chunk] = []
        for b in parts:
            s = (b or "").strip()
            if not s:
                continue
            if len(s) <= max_chars:
                out.append(_Chunk(s, source="ctx"))
            else:
                # divide por sentenças
                cur = ""
                for p in re.split(r"(?<=[\.\!\?])\s+", s):
                    if len(cur) + len(p) + 1 <= max_chars:
                        cur = (cur + " " + p).strip()
                    else:
                        if cur:
                            out.append(_Chunk(cur, source="ctx"))
                        cur = p
                if cur:
                    out.append(_Chunk(cur, source="ctx"))
            if len(out) >= max_chunks:
                break
        return out

    def retrieve(self, query: str, k: int = 6) -> List[_Chunk]:
        pool: List[_Chunk] = []
        for r in self.retrievers:
            try:
                if hasattr(r, "retrieve"):
                    pool.extend(r.retrieve(query, k=k))
                elif hasattr(r, "buscar_chunks"):
                    xs = r.buscar_chunks(query, k=k) or []
                    pool.extend([_Chunk(getattr(x, "text", str(x))) for x in xs[:k]])
                elif hasattr(r, "buscar_contexto"):
                    ctx = r.buscar_contexto(query, k=k) or ""
                    pool.extend(self._split_ctx(ctx, max_chars=self.chunk_max_chars, max_chunks=k))
            except Exception:
                logging.exception("CombinedRetriever: falha em %s", type(r).__name__)
        # dedup simples por texto
        seen = set()
        uniq: List[_Chunk] = []
        for c in pool:
            t = (getattr(c, "text", "") or "").strip()
            if not t or t in seen:
                continue
            seen.add(t)
            uniq.append(c)
            if len(uniq) >= k:
                break
        return uniq