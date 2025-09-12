"""Utilitários e wrappers para uso do Tavily."""

from typing import Any, Dict

from tavily import TavilyClient as _BaseTavilyClient


MAX_QUERY_LEN = 400


class TavilyClient(_BaseTavilyClient):
    """Subclasse que impõe limite de tamanho às consultas.

    A API do Tavily aceita no máximo 400 caracteres na query; consultas maiores
    resultam em erro. Esta subclasse aparará qualquer texto excedente antes de
    delegar para a implementação original.
    """

    @staticmethod
    def _trim(query: str) -> str:
        if isinstance(query, str) and len(query) > MAX_QUERY_LEN:
            return query[:MAX_QUERY_LEN]
        return query

    def search(self, query: str, *args, **kwargs):  # type: ignore[override]
        query = self._trim(query)
        return super().search(query=query, *args, **kwargs)

    # Algumas versões do client expõem ``search_and_summarize``. Garantimos o
    # mesmo comportamento com truncamento da query quando disponível.
    def search_and_summarize(self, query: str, *args, **kwargs):  # type: ignore[override]
        query = self._trim(query)
        return super().search_and_summarize(query=query, *args, **kwargs)


class TavilyService:
    """Wrapper minimalista para o Tavily. Retorna texto e fontes."""
    
    def __init__(self, api_key: str, max_results: int = 6, depth: str = "advanced"):
        self.client = TavilyClient(api_key=api_key)
        self.max_results = max_results
        self.depth = depth  # "basic" | "advanced"

    def buscar(self, consulta: str) -> Dict[str, Any]:
        try:
            resp = self.client.search(
                query=consulta,
                search_depth=self.depth,
                max_results=self.max_results,
                include_answers=True,
                include_images=False,
                include_raw_content=False,
            )
            fontes = [{"titulo": r.get("title"), "url": r.get("url")} for r in resp.get("results", [])]
            texto = resp.get("answer") or "\n\n".join(
                (r.get("content") or "").strip() for r in resp.get("results", []) if r.get("content")
            )
            return {"texto": (texto or ""), "fontes": fontes, "erro": None}
        except Exception as e:
            return {"texto": "", "fontes": [], "erro": str(e)}
