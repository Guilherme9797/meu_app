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
            items = res.get("results", []) if isinstance(res, dict) else []
            top = []
            for it in items[:3]:
                title = it.get("title") or ""
                content = (it.get("content") or "")[:500]
                url = it.get("url") or ""
                top.append(f"- {title}\n  {content}\n  Fonte: {url}")
            return "\n".join(top) or str(res)
        except Exception:
            logging.exception("Falha na busca web.")
            return ""

    # ------------------------------------------------------------------
    # Rotina principal (simplificada)
    # ------------------------------------------------------------------
    
    def handle_message(self, phone: str, text: str) -> str:
        """Compatibilidade com despachantes que passam phone/text."""
        return self.responder(text)
    
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
        messages = [
            {"role": "system", "content": self.conf.system_prompt},
            {"role": "user", "content": prompt},
        ]

        # LLM/Guard (simplificado)
        try:
            if hasattr(self.llm, "generate"):
                raw = self.llm.generate(messages, temperature=0.2, max_tokens=900)
            elif hasattr(self.llm, "chat"):
                raw = self.llm.chat(
                    system=self.conf.system_prompt,
                    user=prompt,
                    extra={"temperature": 0.2, "max_tokens": 900},
                )
            elif hasattr(self.llm, "complete"):
                raw = self.llm.complete(
                    f"[SYSTEM]: {self.conf.system_prompt}\n[USER]: {prompt}"
                )
            elif callable(self.llm):
                raw = self.llm(prompt)
            else:
                raw = ""
        except Exception:
            logging.exception("Falha no LLM.")
            raw = ""

        def _too_similar(a: str, b: str) -> bool:
            a = (a or "").strip()
            b = (b or "").strip()
            if not a or not b:
                return False
            return a == b or a.startswith(b) or b.startswith(a)

        if not raw or _too_similar(raw, prompt) or _too_similar(raw, user_text):
            try:
                if hasattr(self.llm, "generate"):
                    raw = self.llm.generate(
                        [
                            {
                                "role": "system",
                                "content": "Você é um advogado brasileiro. Responda sem ecoar a pergunta.",
                            },
                            {"role": "user", "content": user_text},
                        ],
                        temperature=0.2,
                        max_tokens=700,
                    )
                else:
                    raw = ""
            except Exception:
                logging.exception("Retry do LLM falhou.")
                raw = ""

        if not raw:
            raw = (
                "Orientação preliminar (sem fonte):\n"
                "• Passos práticos ...\n"
                "• Fundamentos possíveis ...\n"
                "• Checklist de documentos ..."
            )

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

    # Tenta usar o cliente oficial baseado em OpenAI; se indisponível, usa um
    # stub que mantém a interface esperada pelo serviço.
    try:
        from meu_app.utils.openai_client import LLM as OpenAILLM  # type: ignore
    except Exception:
        OpenAILLM = None  # type: ignore

    class LLMStub:
        def generate(self, *a, **kw):
            return ""

        def chat(self, *a, **kw):
            return ""

        def complete(self, *a, **kw):
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
    tavily = None
    api_key = os.getenv("TAVILY_API_KEY")
    if api_key and TavilyClient:
        try:
            tavily = TavilyClient(api_key=api_key)
        except Exception as e:
            logging.exception("Falha ao instanciar TavilyClient: %s", e)
            tavily = None

    llm = LLMStub()
    if OpenAILLM is not None:
        try:
            llm = OpenAILLM()
        except Exception:
            llm = LLMStub()
    guard = GroundingGuard()
    classifier = Classifier()
    extractor = Extractor()
    sess_repo = SessionRepository()
    msg_repo = MessageRepository()
    conf = AtendimentoConfig(use_web=tavily is not None)

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

