from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..utils.openai_client import LLM

if TYPE_CHECKING:  # imports apenas para type-checkers
    from .analisador import Classifier, Extractor
    from .buscador_pdf import Retriever, RetrievedChunk
    from .tavily_service import TavilyClient, WebEvidence
    from .refinador import GroundingGuard, GroundedContext
    from ..persistence.repositories import SessionRepository, MessageRepository
else:  # fallback em runtime quando módulos não estiverem disponíveis
    Classifier = Extractor = Retriever = RetrievedChunk = TavilyClient = WebEvidence = GroundingGuard = GroundedContext = Any  # type: ignore
    SessionRepository = MessageRepository = Any  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class AtendimentoConfig:
    """Parâmetros de orquestração ajustáveis sem mexer no código."""
    coverage_threshold: float = 0.55
    max_pdf_chunks: int = 6
    max_web_results: int = 4
    use_web_fallback: bool = True
    temperature: float = 0.2
    append_low_coverage_note: bool = True


class AtendimentoService:

    """
    Orquestra o pipeline do atendimento jurídico:
      1) Classificar intenção/tema e extrair entidades
      2) RAG nos PDFs
      3) Fallback Tavily se cobertura insuficiente (opcional)
      4) Prompt anti-alucinação que NÃO expõe fontes ao cliente
      5) Persistência (sessão, mensagens, fontes apenas para auditoria)

    """

    def __init__(
        self,
        sess_repo: SessionRepository,
        msg_repo: MessageRepository,
        retriever: Retriever,
        tavily: TavilyClient,
        llm: LLM,
        guard: GroundingGuard,
        classifier: Optional[Classifier] = None,
        extractor: Optional[Extractor] = None,
        conf: Optional[AtendimentoConfig] = None,
    ) -> None:
        self.sess_repo = sess_repo
        self.msg_repo = msg_repo
        self.retriever = retriever
        self.tavily = tavily
        self.llm = llm
        self.guard = guard
        self.classifier = classifier or Classifier()
        self.extractor = extractor or Extractor()
        self.conf = conf or AtendimentoConfig()

    # ------------------ API pública ------------------

    def handle_incoming(
        self,
        client_phone: str,
        user_text: str,
        provider_msg_id: Optional[str] = None,
    ) -> str:
        """Ponto de entrada principal do atendimento."""
        if provider_msg_id and self.msg_repo.exists_provider_msg(provider_msg_id):
            logger.info("Ignorando mensagem duplicada provider_msg_id=%s", provider_msg_id)
            return "Mensagem recebida."

        session = self.sess_repo.get_or_create(client_phone)

        intent, tema = self.classifier.classify(user_text)
        ents = self.extractor.extract(user_text)

        pdf_chunks = self._retrieve_pdfs(user_text, tema, ents, k=self.conf.max_pdf_chunks)
        coverage = self.guard.coverage_score(pdf_chunks, user_text)

        web_evidence: List[WebEvidence] = []
        if coverage < self.conf.coverage_threshold and self.conf.use_web_fallback:
            try:
                web_evidence = self.tavily.search_and_summarize(
                    query=user_text, tema=tema, top_k=self.conf.max_web_results
                )
            except Exception as e:  # pragma: no cover - log only
                logger.exception("Falha na busca web (fallback): %s", e)
                web_evidence = []

        grounded_ctx: GroundedContext = self.guard.build_context(pdf_chunks, web_evidence)
        prompt: str = self.guard.build_prompt(user_text, grounded_ctx)
        reply: str = self.llm.generate(prompt, temperature=self.conf.temperature)

        if coverage < self.conf.coverage_threshold and self.conf.append_low_coverage_note:
            reply += (
                "\n\nObservação: com base nas informações e documentos disponíveis até o momento, "
                "esta orientação é preliminar. Para maior precisão, envie o documento/decisão/contrato relacionado "
                "ou detalhe datas, valores e comarca."
            )

        try:
            self.msg_repo.save_in_out(
                session_id=session.id,
                provider_msg_id=provider_msg_id,
                user_msg=user_text,
                reply=reply,
                topic=tema,
                intent=intent,
                entities=ents,
                sources=grounded_ctx.sources_for_audit(),
            )
        except Exception as e:  # pragma: no cover - persistence best effort
            logger.exception("Falha ao persistir troca de mensagens: %s", e)
    
        try:
            self.sess_repo.update_phase_if_ready(session.id, reply)
        except Exception as e:  # pragma: no cover - best effort
            logger.exception("Falha ao avaliar mudança de fase: %s", e)

        return reply
        
        # ------------------ Helpers internos ------------------

        def _retrieve_pdfs(
            self, query: str, tema: Optional[str], ents: Dict[str, Any], k: int
        ) -> List[RetrievedChunk]:
            try:
                return self.retriever.retrieve(query=query, tema=tema, ents=ents, k=k)
            except Exception as e:  # pragma: no cover - log and fallback
                logger.exception("Falha no retriever: %s", e)
                return []

# Compatibilidade: manter nome antigo
Atendimento = AtendimentoService