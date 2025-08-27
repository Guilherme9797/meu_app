from typing import Dict, Any
from tavily import TavilyClient

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
