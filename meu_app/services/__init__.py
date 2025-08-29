from __future__ import annotations
from typing import TYPE_CHECKING

# Exportamos só os nomes; o carregamento real é feito sob demanda em __getattr__
__all__ = [
   "Classifier",
    "Extractor",
    "Retriever",
    "GroundingGuard",
    "TavilyClient",
    "ZapiClient",
    "AtendimentoService",
    "MediaProcessor",
]

def __getattr__(name: str):
    # Núcleo
    if name == "Classifier":
        from .analisador import Classifier
        return Classifier
    if name == "Extractor":
        from .analisador import Extractor
        return Extractor
    if name == "Retriever":
        from .buscador_pdf import Retriever
        return Retriever
    if name == "GroundingGuard":
        from .refinador import GroundingGuard
        return GroundingGuard
    if name == "TavilyClient":
        from .tavily_service import TavilyClient
        return TavilyClient
    if name == "ZapiClient":
        from .zapi_client import ZapiClient
        return ZapiClient
    if name == "ZApiClient":
        from .zapi_client import ZapiClient
        return ZapiClient
    if name == "AtendimentoService":
        from .atendimento import AtendimentoService
        return AtendimentoService
    if name == "MediaProcessor":
        from .media_processor import MediaProcessor
        return MediaProcessor
    if name == "AnalisadorDeProblemas":
        from .analisador import Classifier
        return Classifier
    if name == "BuscadorPDF":
        from .buscador_pdf import Retriever
        return Retriever
    if name == "RefinadorResposta":
        from .refinador import GroundingGuard
        return GroundingGuard
    if name == "Atendimento":
        from .atendimento import AtendimentoService
        return AtendimentoService
    if name == "PDFIndexer":
        from .pdf_indexer import main as PDFIndexer
        return PDFIndexer
    if name == "ConversorPropostas":
        class _Placeholder:
            pass
        return _Placeholder


    # Pagamentos (opcionais)
    if name == "PaymentOrchestrator":
        from .payments.orchestrator import PaymentOrchestrator
        return PaymentOrchestrator
    if name in {"PaymentProvider", "CheckoutResult"}:
        try:
            from .payments.base import PaymentProvider, CheckoutResult
            return {"PaymentProvider": PaymentProvider, "CheckoutResult": CheckoutResult}[name]
        except Exception:
            # Ambiente parcial: manter compatibilidade sem quebrar import
            return None

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def __dir__():
    return sorted(__all__)

# Ajuda para type checkers (mypy/pyright) sem forçar import em runtime
if TYPE_CHECKING:
    from .analisador import Classifier, Extractor
    from .buscador_pdf import Retriever
    from .refinador import GroundingGuard
    from .tavily_service import TavilyClient
    from .zapi_client import ZApiClient
    from .atendimento import AtendimentoService
    from .media_processor import MediaProcessor
    