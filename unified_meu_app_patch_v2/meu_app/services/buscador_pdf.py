from __future__ import annotations
from typing import Optional, Dict, Any

if __package__ is None or __package__ == "":
    import os, sys
    _here = os.path.abspath(__file__)
    _services_dir = os.path.dirname(_here)
    _project_root = os.path.dirname(os.path.dirname(_services_dir))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from meu_app.services.pdf_indexer import PDFIndexer
    try:
        from meu_app.services.tavily_service import TavilyService
    except Exception:
        TavilyService = None  # type: ignore
else:
    from .pdf_indexer import PDFIndexer
    try:
        from .tavily_service import TavilyService
    except Exception:
        TavilyService = None  # type: ignore

class BuscadorPDF:
    """Primeiro consulta o índice local; se insuficiente, busca externa (Tavily)."""
    def __init__(
        self,
        openai_key: str,
        tavily_key: Optional[str] = None,
        pdf_dir: str = "data/pdfs",
        index_dir: str = "index/faiss_index",
        *,
        pasta_pdfs: Optional[str] = None,
        pasta_index: Optional[str] = None,
    ):
        # aliases (compat com server.py)
        pdf_dir = pasta_pdfs or pdf_dir
        index_dir = pasta_index or index_dir

        self.indexador = PDFIndexer(pasta_pdfs=pdf_dir, pasta_index=index_dir, openai_key=openai_key)
        if not self.indexador.load_index():
            self.indexador.indexar_pdfs()
            self.indexador.load_index()

        self.tavily = (TavilyService(api_key=tavily_key) if (tavily_key and TavilyService) else None)
        self._min_chars_pdf = 400

    def atualizar_indice_verbose(self) -> Dict[str, Any]:
        return self.indexador.atualizar_indice_verbose()

    def buscar_resposta(self, problema: str) -> str:
        texto_pdf = self.indexador.buscar_resposta(pergunta=problema, k=6, max_distance=0.35) or ""
        if len(texto_pdf.strip()) >= self._min_chars_pdf:
            return texto_pdf

        if self.tavily:
            tv = self.tavily.buscar(problema)
            if isinstance(tv, dict) and tv.get("erro"):
                return f"[Falha no Tavily: {tv['erro']}]\n\n{texto_pdf}".strip()

            fontes = ""
            if isinstance(tv, dict) and tv.get("fontes"):
                fontes = "\n\nFontes (Tavily):\n" + "\n".join(
                    f"- {f.get('titulo') or 'Fonte'}: {f.get('url')}" for f in tv["fontes"] if f.get("url")
                )

            base = (tv.get("texto") if isinstance(tv, dict) else "") or texto_pdf
            return (base + (fontes if fontes else "")).strip()

        return texto_pdf

    def buscar_na_internet(self, problema: str) -> str:
        if not self.tavily:
            return "[Tavily não configurado]"
        tv = self.tavily.buscar(problema)
        if isinstance(tv, dict) and tv.get("erro"):
            return f"[Falha no Tavily: {tv['erro']}]"
        fontes = ""
        if isinstance(tv, dict) and tv.get("fontes"):
            fontes = "\n\nFontes (Tavily):\n" + "\n".join(
                f"- {f.get('titulo') or 'Fonte'}: {f.get('url')}" for f in tv["fontes"] if f.get("url")
            )
        return ((tv.get("texto") if isinstance(tv, dict) else "") or "") + (fontes if fontes else "")

    def buscar_contexto(self, consulta: str, k: int = 5) -> str:
        return self.indexador.buscar_contexto(consulta, k=k)
