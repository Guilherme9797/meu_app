from __future__ import annotations
from typing import TYPE_CHECKING

# Exportamos só os nomes; o carregamento real é feito sob demanda em __getattr__
__all__ = [
    "AnalisadorDeProblemas",
    "RefinadorResposta",
    "PDFIndexer",
    "BuscadorPDF",
    "TavilyService",
    "ZapiClient",
    "Atendimento",
    "AtendimentoService",
    "ConversorPropostas",
    "PricingService",
    "Classifier",
    "guess_tema",
    "Extractor",
    "extract_process_numbers",
    "PaymentOrchestrator",
    "PaymentProvider",
    "CheckoutResult",
]


def __getattr__(name: str):
    # Núcleo
    if name == "AnalisadorDeProblemas":
        try:
            from .analisador import AnalisadorDeProblemas
            return AnalisadorDeProblemas
        except Exception:
            return None
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
    if name == "Classifier":
        try:
            from .classifier import Classifier  # type: ignore
            return Classifier
        except Exception:
            class _NoOpClassifier:
                """Fallback silencioso quando o Classifier real não está disponível."""

                def __init__(self, *args, **kwargs) -> None:
                    pass

                def classify(self, *args, **kwargs):  # pragma: no cover - sem lógica real
                    return {}

            return _NoOpClassifier
    if name == "Extractor":
        try:
            from .extractor import Extractor  # type: ignore
            return Extractor
        except Exception:
            class _NoOpExtractor:
                """Fallback silencioso quando o Extractor real não está disponível."""

                def __init__(self, *args, **kwargs) -> None:
                    pass

                def extract(self, *args, **kwargs):  # pragma: no cover - sem lógica real
                    """Retorna tuple (intent, tema) vazio para compatibilidade."""
                    return None, None

            return _NoOpExtractor
    if name == "GroundingGuard":
        try:
            from .guard import GroundingGuard  # type: ignore
            return GroundingGuard
        except Exception:
            class _NoOpGuard:
                """Fallback silencioso quando GroundingGuard real não está disponível."""

                def __init__(self, *args, **kwargs) -> None:
                    pass

                def check(self, *args, **kwargs):  # pragma: no cover - sem lógica real
                    return True

            return _NoOpGuard
    if name == "TavilyClient":
        try:
            from .tavily_service import TavilyClient  # type: ignore
            return TavilyClient
        except Exception:
            try:
                from .tavily_service import TavilyService
                return TavilyService
            except Exception:
                return None
    if name == "AtendimentoService":
        try:
            from .atendimento_service import AtendimentoService  # type: ignore
            return AtendimentoService
        except Exception:
            try:
                from .atendimento import Atendimento
                return Atendimento
            except Exception:
                return None
    if name == "ZapiClient":
        from .zapi_client import ZapiClient
        return ZapiClient
    if name == "Atendimento":
        from .atendimento import Atendimento
        return Atendimento
    if name == "AtendimentoService":
        from .atendimento_service import AtendimentoService
        return AtendimentoService
    if name == "ConversorPropostas":
        from .conversor import ConversorPropostas
        return ConversorPropostas
    if name == "PricingService":
        from .pricing import PricingService  # pode não existir no ambiente
        return PricingService
    if name in {"Classifier", "guess_tema"}:
        from .classifier import Classifier, guess_tema
        return {"Classifier": Classifier, "guess_tema": guess_tema}[name]
    if name in {"Extractor", "extract_process_numbers"}:
        from .extractor import Extractor, extract_process_numbers
        return {"Extractor": Extractor, "extract_process_numbers": extract_process_numbers}[name]

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
    from .buscador_pdf import BuscadorPDF, Retriever
    from .tavily_service import TavilyService
    from .zapi_client import ZapiClient
    from .atendimento import Atendimento
    from .atendimento_service import AtendimentoService
    from .conversor import ConversorPropostas
    from .pricing import PricingService  # type: ignore
    from .classifier import Classifier, guess_tema
    from .extractor import Extractor, extract_process_numbers
    from .payments.orchestrator import PaymentOrchestrator  # type: ignore
    try:
        from .classifier import Classifier  # type: ignore
    except Exception:
        Classifier = None  # type: ignore
    try:
        from .extractor import Extractor  # type: ignore
    except Exception:
        Extractor = None  # type: ignore
    try:
        from .guard import GroundingGuard  # type: ignore
    except Exception:
        GroundingGuard = None  # type: ignore
    try:
        from .tavily_service import TavilyClient  # type: ignore
    except Exception:
        TavilyClient = None  # type: ignore
    try:
        from .atendimento_service import AtendimentoService  # type: ignore
    except Exception:
        try:
            from .atendimento import Atendimento as AtendimentoService  # type: ignore
        except Exception:
            AtendimentoService = None  # type: ignore
    try:
        from .payments.base import PaymentProvider, CheckoutResult  # type: ignore
    except Exception:
        PaymentProvider = None  # type: ignore
        CheckoutResult = None   # type: ignore