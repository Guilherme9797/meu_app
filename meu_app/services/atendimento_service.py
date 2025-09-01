from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AtendimentoConfig:
    """Configuração básica do fluxo de atendimento."""

    system_prompt: str = (
        "Você é um assistente jurídico que responde de forma direta e concisa."
    )
    retriever_k: int = 3


class AtendimentoService:
    """Pipeline de atendimento simplificado para a CLI.

    Esta implementação foi projetada para ser resiliente a faltas de
    dependências opcionais. Cada etapa do fluxo (classificação,
    extração de entidades, busca em PDFs e geração da resposta) tenta
    executar seu passo correspondente, mas falha silenciosamente caso
    a funcionalidade não esteja disponível.
    """

    def __init__(
        self,
        *,
        sess_repo: Any,
        msg_repo: Any,
        retriever: Any,
        tavily: Any,
        llm: Any,
        guard: Any,
        classifier: Any,
        extractor: Any,
        conf: AtendimentoConfig,
    ) -> None:
        self.sess_repo = sess_repo
        self.msg_repo = msg_repo
        self.retriever = retriever
        self.tavily = tavily
        self.llm = llm
        self.guard = guard
        self.classifier = classifier
        self.extractor = extractor
        self.conf = conf

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------
    def _safe_classify(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Retorna (intent, tema) sem levantar exceções."""
        intent: Optional[str] = None
        tema: Optional[str] = None
        try:
            result = self.classifier.classify(text)
            if isinstance(result, (list, tuple)):
                if len(result) >= 2:
                    intent, tema = result[0], result[1]
            elif isinstance(result, dict):
                intent = result.get("intent")
                tema = result.get("tema")
        except Exception:
            pass
        return intent, tema

    def _safe_extract(self, text: str) -> Dict[str, Any]:
        try:
            data = self.extractor.extract(text) or {}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _safe_retrieve(
        self, query: str, tema: Optional[str], ents: Dict[str, Any]
    ) -> List[Any]:
        try:
            return self.retriever.retrieve(query=query, tema=tema, ents=ents, k=self.conf.retriever_k)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def handle_incoming(self, session_id: str, user_text: str) -> str:
        """Processa uma mensagem do usuário e retorna a resposta."""
        # registra mensagem recebida
        try:
            self.msg_repo.save(session_id, "user", user_text)
        except Exception:
            pass

        intent, tema = self._safe_classify(user_text)
        ents = self._safe_extract(user_text)
        chunks = self._safe_retrieve(user_text, tema, ents)
        context = "\n\n".join(getattr(c, "text", str(c)) for c in chunks)

        prompt = user_text
        if context:
            prompt = f"{user_text}\n\nContexto:\n{context}"

        try:
            answer = self.llm.chat(self.conf.system_prompt, prompt)
        except Exception:
            answer = "Desculpe, não consegui gerar uma resposta agora."

        # registra resposta
        try:
            self.msg_repo.save(session_id, "assistant", answer)
        except Exception:
            pass

        return answer