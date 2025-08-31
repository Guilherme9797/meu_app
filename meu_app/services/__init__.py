from __future__ import annotations
from typing import TYPE_CHECKING

# Exportamos só os nomes; o carregamento real é feito sob demanda em __getattr__
__all__ = [
    "AnalisadorDeProblemas",
    "RefinadorResposta",
    "PDFIndexer",
    "BuscadorPDF",
    "Retriever",
    "TavilyService",
    "ZapiClient",
    "Atendimento",
    "Classifier",
    "Extractor",
    "GroundingGuard",
    "TavilyClient",
    "AtendimentoService",
    "ConversorPropostas",
    "PricingService",
    "PaymentOrchestrator",
    "PaymentProvider",
    "CheckoutResult",
]


def __getattr__(name: str):
    # Núcleo
    if name == "AnalisadorDeProblemas":
        from .analisador import AnalisadorDeProblemas
        return AnalisadorDeProblemas
    if name == "RefinadorResposta":
        from .refinador import RefinadorResposta
        return RefinadorResposta
    if name == "PDFIndexer":
        from .pdf_indexer import PDFIndexer
        return PDFIndexer
    if name == "BuscadorPDF":
        from .buscador_pdf import BuscadorPDF
        return BuscadorPDF
    if name == "Retriever":
        from .buscador_pdf import Retriever
        return Retriever
    if name == "TavilyService":
        from .tavily_service import TavilyService
        return TavilyService
    if name == "ZapiClient":
        from .zapi_client import ZapiClient
        return ZapiClient
    if name == "Atendimento":
        from .atendimento import Atendimento
        return Atendimento
    if name == "ConversorPropostas":
        from .conversor import ConversorPropostas
        return ConversorPropostas
    if name == "PricingService":
        from .pricing import PricingService  # pode não existir no ambiente
        return PricingService

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
    from .analisador import AnalisadorDeProblemas
    from .refinador import RefinadorResposta
    from .pdf_indexer import PDFIndexer
    from .buscador_pdf import BuscadorPDF
    from .buscador_pdf import BuscadorPDF, Retriever
    from .tavily_service import TavilyService
    from .zapi_client import ZapiClient
    from .atendimento import Atendimento
    from .conversor import ConversorPropostas
    from .pricing import PricingService  # type: ignore
    from .payments.orchestrator import PaymentOrchestrator  # type: ignore
    try:
        from .payments.base import PaymentProvider, CheckoutResult  # type: ignore
    except Exception:
        PaymentProvider = None  # type: ignore
        CheckoutResult = None   # type: ignore
    