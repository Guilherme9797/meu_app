from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass
class AtendimentoConfig:
    """Configurações do AtendimentoService."""
    system_prompt: str = "Você é um assistente jurídico..."
    retriever_k: int = 4
    max_context_chars: int = 4500
    coverage_threshold: float = 0.40   # abaixo disso, tenta web
    use_web: bool = True               # habilita web no builder


class AtendimentoService:
    """Serviço de atendimento com recuperação de PDFs e busca web opcional."""

    def __init__(
        self,
        sess_repo: Any,
        msg_repo: Any,
        retriever: Any,
        tavily: Any = None,
        llm: Any = None,
        guard: Any = None,
        classifier: Any = None,
        extractor: Any = None,
        conf: Optional[AtendimentoConfig] = None,
    ) -> None:
        self.sess_repo = sess_repo
        self.msg_repo = msg_repo
        self.retriever = retriever
        self.tavily = tavily
        self.llm = llm
        self.guard = guard
        self.classifier = classifier
        self.extractor = extractor
        self.conf = conf or AtendimentoConfig()

    # ------------------------------------------------------------------
    # Helpers de classificação
    # ------------------------------------------------------------------
    def _infer_default_tema(self, text: str) -> str:
        """Heurística simples para tema padrão."""
        return "geral"

    def _safe_classify(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Retorna (intent, tema) sem levantar exceções, compatível com várias interfaces."""

        def _raw_call(c, t):
            # tenta vários formatos
            if hasattr(c, "classify"):
                return c.classify(t)
            if hasattr(c, "predict"):
                return c.predict(t)
            if hasattr(c, "infer"):
                return c.infer(t)
            if callable(c):
                return c(t)
            return None

        intent: Optional[str] = None
        tema: Optional[str] = None
        try:
            c = self.classifier
            res = _raw_call(c, text)

            # se veio uma classe em vez de instância, tente instanciar e chamar
            if res is None and isinstance(c, type):
                try:
                    self.classifier = c()  # salva a instância para os próximos calls
                    res = _raw_call(self.classifier, text)
                except Exception:
                    res = None

            # normaliza saída
            if isinstance(res, (list, tuple)):
                if len(res) >= 2:
                    intent, tema = res[0], res[1]
                elif len(res) == 1:
                    intent = res[0]
            elif isinstance(res, dict):
                intent = res.get("intent") or res.get("label")
                tema = res.get("tema") or res.get("topic") or res.get("category")
            elif isinstance(res, str):
                intent = res
        except Exception:
            # Evite matar o fluxo por causa do classificador
            logging.exception("Falha ao classificar.")

        # Defaults úteis
        if not intent:
            intent = "consulta"
        if not tema:
            tema = self._infer_default_tema(text)
        return intent, tema

    # ------------------------------------------------------------------
    # Recuperação e web
    # ------------------------------------------------------------------
    def _safe_retrieve(self, query: str, tema: Optional[str] = None, ents: Optional[List[str]] = None) -> List[Any]:
        try:
            if hasattr(self.retriever, "retrieve"):
                return list(self.retriever.retrieve(query, k=self.conf.retriever_k))
        except Exception:
            logging.exception("Falha na recuperação.")
        return []

    def _score_pdf_coverage(self, chunks: List[Any]) -> float:
        if not chunks:
            return 0.0
        return min(1.0, len(chunks) / float(self.conf.retriever_k))

    def _safe_web_search(self, query: str) -> str:
        try:
            if not self.conf.use_web or not getattr(self, "tavily", None):
                return ""
            res = self.tavily.search(query)
            if not res:
                return ""
            if isinstance(res, str) and "tavily" in res.lower() and "não configurado" in res.lower():
                logging.info("Tavily não configurado; ignorando web.")
                return ""
            if isinstance(res, dict) and (res.get("error") or res.get("ok") is False):
                logging.warning("Erro Tavily: %r", res)
                return ""
            return str(res)
        except Exception:
            logging.exception("Falha na busca web.")
            return ""

    # ------------------------------------------------------------------
    # Rotina principal (simplificada)
    # ------------------------------------------------------------------
    def responder(self, user_text: str) -> str:
        """Gera resposta usando PDFs e, se necessário, busca web."""
        intent, tema = self._safe_classify(user_text)
        ents: List[str] = []
        chunks = self._safe_retrieve(user_text, tema, ents)
        pdf_ctx = "\n\n".join(getattr(c, "text", str(c)) for c in chunks) if chunks else ""
        coverage = self._score_pdf_coverage(chunks)

        web_ctx = ""
        if coverage < self.conf.coverage_threshold:
            web_ctx = self._safe_web_search(user_text)

        parts = [p for p in (pdf_ctx, web_ctx) if p]
        context = ("\n\n".join(parts))[: self.conf.max_context_chars]
        if context:
            prompt = (
                f"{user_text}\n\n"
                "Responda de forma orientada à ação (o que fazer, por quê, como). "
                "Use APENAS o CONTEXTO abaixo, sem citar nomes de documentos ou URLs.\n\n"
                f"CONTEXTO:\n{context}"
            )
        else:
            prompt = (
                f"{user_text}\n\n"
                "Sem materiais auxiliares. Ainda assim, dê instruções práticas (o que fazer, por quê, como) "
                "e um checklist de documentos."
            )

        # LLM/Guard (simplificado)
        try:
            if hasattr(self.llm, "complete"):
                raw = self.llm.complete(prompt)
            elif callable(self.llm):
                raw = self.llm(prompt)
            else:
                raw = prompt
        except Exception:
            logging.exception("Falha no LLM.")
            raw = prompt

        return raw


# ------------------------------------------------------------------------------
# Builder auxiliar
# ------------------------------------------------------------------------------

def get_index_dir() -> str:
    return os.getenv("INDEX_DIR", "index/faiss_index")


def _build_atendimento_service() -> AtendimentoService:
    """Constrói um AtendimentoService com dependências padrão."""
    try:
        from tavily import TavilyClient
    except Exception:  # pragma: no cover - opcional
        TavilyClient = None  # type: ignore

    # Dependências básicas (stubs se não houver implementações reais)
    class Embeddings:
        def embed(self, text: str) -> List[float]:
            return []

    class Retriever:
        def __init__(self, index_path: str, embed_fn: Any = None) -> None:
            self.index_path = index_path
            self.embed_fn = embed_fn

        def retrieve(self, query: str, k: int = 4) -> List[Any]:
            return []

    class LLM:
        def complete(self, prompt: str) -> str:
            return ""

    class GroundingGuard:
        def verify(self, text: str) -> bool:
            return True

    class Classifier:
        pass

    class Extractor:
        pass

    class SessionRepository:
        pass

    class MessageRepository:
        pass

    embedder = Embeddings()
    retriever = Retriever(index_path=get_index_dir(), embed_fn=getattr(embedder, "embed", None))

    use_tavily = os.getenv("MEU_APP_USE_TAVILY", "0").lower() in ("1", "true", "yes", "on")
    tavily = None
    if use_tavily and TavilyClient:
        try:
            if hasattr(TavilyClient, "from_env"):
                tavily = TavilyClient.from_env()
            else:
                tavily = TavilyClient()
        except Exception:
            tavily = None

    llm = LLM()
    guard = GroundingGuard()
    classifier = Classifier()
    extractor = Extractor()
    sess_repo = SessionRepository()
    msg_repo = MessageRepository()
    conf = AtendimentoConfig(use_web=use_tavily)

    return AtendimentoService(
        sess_repo=sess_repo,
        msg_repo=msg_repo,
        retriever=retriever,
        tavily=tavily,
        llm=llm,
        guard=guard,
        classifier=classifier,
        extractor=extractor,
        conf=conf,
    )