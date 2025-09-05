from __future__ import annotations
from typing import Any, List, Dict

class BNPProvider:
    """
    Busca 'precedentes qualificados' usando o Tavily com filtro de domínio
    para pdpj/pangeabnp. Como a BNP não expõe API pública aberta,
    usamos snippets/títulos públicos via web search.
    """
    def __init__(self, tavily_client: Any | None):
        self.tavily = tavily_client

    def _mk_queries(self, user_text: str, tags: List[str]) -> List[str]:
        base = user_text.strip()
        bt = " ".join(tags[:3]) if tags else ""
        seeds = [
            base,
            f'{base} {bt}'.strip(),
            f'{base} tese repetitivo',
            f'{base} IRDR IAC precedente qualificado',
        ]
        # força recorte de domínio (funciona bem com provedores de busca)
        return [f'site:pdpj.jus.br {q}' for q in seeds] + \
               [f'site:pangeabnp.pdpj.jus.br {q}' for q in seeds]

    def search_precedents(self, user_text: str, frame: Dict, limit: int = 6) -> List[Dict]:
        if not self.tavily:
            return []
        queries = self._mk_queries(user_text, frame.get("tags") or [])
        chunks: List[Dict] = []
        seen_urls = set()
        for q in queries[:4]:
            try:
                res = self.tavily.search(q) or {}
            except Exception:
                continue
            items = res.get("results") or []
            for it in items:
                url = (it.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                title = (it.get("title") or "")[:160]
                content = (it.get("content") or "")[:500]
                if not title and not content:
                    continue
                # retornamos como "chunk neutro" (sem URL no texto; URL vai na metadata)
                chunks.append({
                    "text": f"Precedente/nota BNP/PDPJ: {title}. {content}",
                    "source": "bnp_web",
                    "metadata": {"url": url, "origin": "pdpj/pangeabnp"},
                })
                if len(chunks) >= limit:
                    break
            if len(chunks) >= limit:
                break
        return chunks