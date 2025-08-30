from __future__ import annotations
import logging
import os
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
    coverage_threshold: float = 0.55   # suficiência mínima (0..1)
    max_pdf_chunks: int = 6
    max_web_results: int = 4
    use_web_fallback: bool = True
    temperature: float = 0.2
    append_low_coverage_note: bool = True
    min_chunk_score: float = 0.25      # descarta chunks muito fracos
    mmr_lambda: float = 0.6            # 0..1 (1 = só relevância; 0 = só diversidade)
    per_doc_cap: int = 3               # limite de chunks por documento


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

    # Propaga knobs do RAG via ENV (usados pelo Retriever)
        os.environ.setdefault("RAG_MIN_CHUNK_SCORE", str(self.conf.min_chunk_score))
        os.environ.setdefault("RAG_PER_DOC_CAP", str(self.conf.per_doc_cap))
        os.environ.setdefault("RAG_MMR_LAMBDA", str(self.conf.mmr_lambda))
    
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

         # 4.5) Carregar histórico recente (memória curta) para coerência
        try:
            history = self.msg_repo.fetch_history_texts(session.id, limit=10)
        except Exception:  # pragma: no cover - fallback
            history = []

        intent, tema = self.classifier.classify(user_text)
        ents = self.extractor.extract(user_text)

        pdf_chunks = self._retrieve_pdfs(user_text, tema, ents, k=self.conf.max_pdf_chunks)

        if self.conf.min_chunk_score > 0:
            pdf_chunks = [c for c in pdf_chunks if c.score >= self.conf.min_chunk_score]

        if self.conf.per_doc_cap > 0:
            doc_counts: Dict[str, int] = {}
            filtered: List[RetrievedChunk] = []
            for c in pdf_chunks:
                doc_counts[c.doc_id] = doc_counts.get(c.doc_id, 0) + 1
                if doc_counts[c.doc_id] <= self.conf.per_doc_cap:
                    filtered.append(c)
            pdf_chunks = filtered

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
        prompt: str = self.guard.build_prompt(user_text, grounded_ctx, history=history)
        reply: str = self.llm.generate(prompt, temperature=self.conf.temperature)

        if coverage < self.conf.coverage_threshold and self.conf.append_low_coverage_note:
            reply += (
                "\n\nObservação: com base nas informações e documentos disponíveis até o momento, "
                "esta orientação é preliminar. Para maior precisão, envie o documento/decisão/contrato relacionado "
                "ou detalhe datas, valores e comarca."
            )
        retrieval_scores = [
            {
                "doc_id": c.doc_id,
                "title": c.doc_title,
                "span": c.span,
                "score": float(c.score),
            }
            for c in pdf_chunks
        ]

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
                coverage=coverage,
                retrieval_scores=retrieval_scores,
            )
        except Exception as e:  # pragma: no cover - persistence best effort
            logger.exception("Falha ao persistir troca de mensagens: %s", e)
    
        try:
            self.sess_repo.update_phase_if_ready(session.id, reply)
        except Exception as e:  # pragma: no cover - best effort
            logger.exception("Falha ao avaliar mudança de fase: %s", e)

        return reply
        
        # ------------------ Helpers internos ------------------

    def is_issue_resolved(self, user_text: str, reply_text: str) -> bool:
        """Heurística simples para detectar confirmação de resolução."""
        t = (user_text or "").lower()
        r = (reply_text or "").lower()
        triggers = [
            "ok, entendi",
            "entendi, obrigado",
            "perfeito, obrigado",
            "como contrato",
            "como faço para contratar",
            "pode fazer a proposta",
            "quero avançar",
            "vamos prosseguir",
            "pode seguir com a proposta",
        ]
        return any(x in t for x in triggers) or any(x in r for x in triggers)
    
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