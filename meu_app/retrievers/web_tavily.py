# -*- coding: utf-8 -*-
from __future__ import annotations
import os, logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

class Chunk:
    def __init__(self, text: str, source: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        self.text = text
        self.source = source or "web"
        self.metadata = metadata or {}

def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def _default_whitelist() -> List[str]:
    return [
        ".jus.br", ".gov.br", ".mp.br",
        "cnj.jus.br", "stj.jus.br", "tst.jus.br", "tse.jus.br", "stm.jus.br",
        "tj", "trf",
    ]

def _match_whitelist(host: str, whitelist: List[str]) -> bool:
    host = host or ""
    for w in whitelist:
        if w.startswith('.'):
            if host.endswith(w):
                return True
        elif w in host:
            return True
    return False

class WebRetriever:
    def __init__(self, tavily_client: Optional[Any] = None, num_results: int = 8) -> None:
        self.num_results = max(1, min(int(num_results), 20))
        self.cli = tavily_client or self._make_client()
        self.allowed = self._load_list("WEB_ALLOWED_DOMAINS") or _default_whitelist()
        self.blocked = self._load_list("WEB_BLOCKED_DOMAINS") or [
            "youtube.com","facebook.com","tiktok.com","x.com","twitter.com","instagram.com"
        ]

    def _make_client(self):
        try:
            from tavily import TavilyClient
            key = os.getenv("TAVILY_API_KEY")
            if not key:
                raise RuntimeError("TAVILY_API_KEY ausente")
            return TavilyClient(api_key=key)
        except Exception as e:
            raise RuntimeError(f"Tavily não disponível: {e}")

    def _load_list(self, env_name: str) -> List[str]:
        v = (os.getenv(env_name) or "").strip()
        if not v:
            return []
        return [x.strip().lower() for x in v.split(",") if x.strip()]

    def _allowed_url(self, url: str) -> bool:
        host = _domain(url)
        if not host:
            return False
        if any(b in host for b in self.blocked):
            return False
        return _match_whitelist(host, self.allowed)

    def retrieve(self, query: str, k: int = 6) -> List[Chunk]:
        out: List[Chunk] = []
        try:
            res = self.cli.search(query, search_depth="advanced", include_domains=None, exclude_domains=None, max_results=self.num_results)
            items = (res or {}).get("results") or []
            for it in items:
                url = it.get("url") or ""
                if not self._allowed_url(url):
                    continue
                title = (it.get("title") or "").strip()
                content = (it.get("content") or "").strip()
                if not content and not title:
                    continue
                snippet = (title + " — " + content)[:450]
                meta = {"url": url, "title": title}
                out.append(Chunk(text=snippet, source=f"web:{_domain(url)}", metadata=meta))
                if len(out) >= k:
                    break
        except Exception:
            logging.exception("WebRetriever/Tavily falhou.")
        return out