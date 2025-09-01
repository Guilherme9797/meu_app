from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AtendimentoConfig:
    """Configuração básica do fluxo de atendimento."""

    system_prompt: str = (
        "Você é um assistente jurídico. Responda de forma clara e prática, em tópicos de ação "
        "(o que fazer, por quê, como). Se houver CONTEXTO, use-o sem citar nomes de documentos, "
        "trechos, fontes ou URLs. Evite pedir desculpas e evite respostas vagas."
    )
    retriever_k: int = 4
    max_context_chars: int = 4500
    coverage_threshold: float = 0.40   # 0..1 — abaixo disso, tenta web
    use_web: bool = True               # habilitado via builder


class AtendimentoService:
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
    def _infer_default_tema(self, text: str) -> str:
        t = (text or "").lower()
        if any(k in t for k in ("celular","telefone","loja","e-commerce","internet","defeito","garantia","troca","arrependimento","compr")):
            return "consumidor"
        if any(k in t for k in ("plano","saúde","saude","cirurgia","tratamento","sus","hospital")):
            return "saude"
        if any(k in t for k in ("penhora","bloqueio","honor","art. 833","impenhor")):
            return "processo_civil"
        return "geral"

    def _fallback_reply(self, user_text: str, tema: Optional[str], intent: Optional[str]) -> str:
        t = (user_text or "").lower()
        tema = (tema or self._infer_default_tema(user_text)).lower()
        if tema == "consumidor" or any(k in t for k in ("celular","telefone","loja","e-commerce","internet","defeito","garantia","troca","arrependimento","compr")):
            return (
                "Entendi sua situação. Atuamos em duas frentes: (1) notificação extrajudicial para solução rápida; "
                "(2) ação judicial para substituição, restituição/abatimento do preço e, se cabível, dano moral.\n\n"
                "📌 CDC:\n"
                "• Vício do produto: se não sanar em até 30 dias, você pode exigir substituição, restituição ou abatimento (art. 18).\n"
                "• Arrependimento (compra online): 7 dias do recebimento, com devolução integral (art. 49), quando aplicável.\n\n"
                "🧾 Envie: nota fiscal/recibo, comprovantes de pagamento, fotos/vídeos do defeito, protocolos de atendimento, termos de garantia e uma timeline (compra, 1ª reclamação, assistência, negativas).\n\n"
                "➡️ Com isso, preparo a estratégia e já redijo a notificação/ação adequada."
            )
        if tema == "processo_civil" or any(k in t for k in ("honor","penhora","bloqueio","art. 833","impenhor")):
            return (
                "Certo. Podemos levantar a constrição por impenhorabilidade (CPC, art. 833, IV – honorários de natureza alimentar) "
                "com pedido de tutela de urgência e, se for o caso, redirecionamento para valores penhoráveis.\n\n"
                "🧾 Envie: contrato de honorários, comprovantes de recebimento, identificação do processo de origem, extratos com o bloqueio (datas/valores) "
                "e breve explicação da natureza alimentar (subsistência/custeio do escritório).\n\n"
                "➡️ Com isso, protocolamos a impugnação/embargos com pedido liminar."
            )
        return (
            "Posso iniciar pela via extrajudicial e, se necessário, ajuizar a medida adequada. "
            "Me envie os documentos básicos (contratos, comprovantes, comunicações e um resumo cronológico dos fatos) para preparar os próximos passos."
        )

    def _score_pdf_coverage(self, chunks: List[Any]) -> float:
        """Heurística: usa score médio se existir; senão densidade k/retornado."""
        if not chunks:
            return 0.0
        scores = []
        for c in chunks:
            s = getattr(c, "score", None)
            if isinstance(s, (float, int)):
                scores.append(float(s))
        if scores:
            import math
            m = sum(scores) / max(1, len(scores))
            return max(0.0, min(1.0, 1.0 / (1.0 + math.exp(-m))))  # sigmoid
        return min(1.0, len(chunks) / float(self.conf.retriever_k))

    def _collect_pdf_sources(self, chunks: List[Any]) -> List[Dict[str, Any]]:
        out = []
        for c in chunks:
            out.append({
                "type": "pdf",
                "doc_id": getattr(c, "doc_id", None),
                "title": getattr(c, "title", getattr(c, "doc_title", None)),
                "span": getattr(c, "span", None),
                "tema": getattr(c, "tema", None),
                "score": getattr(c, "score", None),
            })
        return out

    def _truncate(self, txt: str, max_chars: int) -> str:
        return txt if len(txt) <= max_chars else txt[:max_chars]

    def _safe_extract(self, text: str) -> Dict[str, Any]:
        try:
            return self.extractor.extract(text)
        except Exception:
            return {}

    def _safe_classify(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Retorna (intent, tema) sem levantar exceções."""
        intent: Optional[str] = None
        tema: Optional[str] = None
        try:
            result = self.classifier.classify(text)
            if isinstance(result, (list, tuple)):
                if len(result) >= 2:
                    intent, tema = result[0], result[1]
                elif len(result) == 1 and result[0]:
                    intent = result[0]
            elif isinstance(result, dict):
                intent = result.get("intent") or result.get("label")
                tema = result.get("tema") or result.get("topic") or result.get("category")
            elif isinstance(result, str):
                intent = result
        except Exception:
            logging.exception("Falha ao classificar.", exc_info=True)
        if not intent:
            intent = "consulta"
        if not tema:
            tema = self._infer_default_tema(text)
        return intent, tema

    def _safe_retrieve(
        self, query: str, tema: Optional[str], ents: Dict[str, Any]
    ) -> List[Any]:
        try:
            return self.retriever.retrieve(query=query, tema=tema, ents=ents, k=self.conf.retriever_k)
        except Exception:
            return []

    def _safe_web_search(self, query: str) -> str:
        """Busca web defensiva: nunca devolve sentinela/erro ao LLM."""
        try:
            if not self.conf.use_web or not getattr(self, "tavily", None):
                return ""
            res = self.tavily.search(query)
            if not res:
                return ""
            if isinstance(res, str) and "tavily" in res.lower() and "não configurado" in res.lower():
                logging.info("Tavily não configurado (sentinela); ignorando web.")
                return ""
            if isinstance(res, dict) and (res.get("error") or res.get("ok") is False):
                logging.warning("Erro Tavily: %r", res)
                return ""
            return str(res)
        except Exception:
            logging.exception("Falha na busca web.", exc_info=True)
            return ""

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
        pdf_ctx = "\n\n".join(getattr(c, "text", str(c)) for c in chunks) if chunks else ""
        coverage = self._score_pdf_coverage(chunks)
        web_ctx = ""
        if coverage < self.conf.coverage_threshold:
            web_ctx = self._safe_web_search(user_text)
        parts = [p for p in (pdf_ctx, web_ctx) if p]
        context = self._truncate("\n\n".join(parts), self.conf.max_context_chars)

        # prompt orientado à ação, sem citar fontes/URLs
        if context:
            prompt = (
                f"{user_text}\n\n"
                "Responda de forma objetiva e orientada à ação (o que fazer, por quê, como), em 3–8 itens. "
                "Use APENAS o CONTEXTO abaixo; NÃO cite fontes, nomes de documentos ou URLs.\n\n"
                f"CONTEXTO:\n{context}"
            )
        else:
            prompt = (
                f"{user_text}\n\n"
                "Sem materiais auxiliares. Ainda assim, responda objetivamente com orientação prática (o que fazer, por quê, como) "
                "e inclua um checklist de documentos."
            )

        try:
            try:
                # Assinatura (system, user)
                answer = self.llm.chat(self.conf.system_prompt, prompt)
            except TypeError:
                # Assinatura (messages=[...])
                messages = [
                    {"role": "system", "content": self.conf.system_prompt},
                    {"role": "user", "content": prompt},
                ]
                answer = self.llm.chat(messages)
        except Exception:
            logging.exception("Falha no LLM.chat; aplicando fallback.", exc_info=True)
            answer = None

        def _looks_like_apology(s: str) -> bool:
            s = (s or "").lower()
            return any(p in s for p in ("desculpe", "não consegui gerar uma resposta", "não foi possível"))
        if not answer or not str(answer).strip() or _looks_like_apology(answer):
            answer = self._fallback_reply(user_text, tema, intent)

        # registra resposta
        try:
            meta = {
                "intent": intent,
                "tema": tema,
                "pdf_coverage": round(coverage, 3),
                "sources": self._collect_pdf_sources(chunks),
                "used_web": bool(web_ctx),
                "resolved_hint": any(s in user_text.lower() for s in ("ok, entendi", "como contrato", "pode prosseguir")),
            }
            try:
                self.msg_repo.save(session_id, "assistant", answer, meta=meta)  # se suportar
            except TypeError:
                self.msg_repo.save(session_id, "assistant", answer)
                try:
                    self.msg_repo.save_meta(session_id, meta)  # opcional, se existir
                except Exception:
                    pass
        except Exception:
            pass

        return answer