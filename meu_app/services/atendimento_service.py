from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass
class AtendimentoConfig:
    """Configurações do AtendimentoService."""
    system_prompt: str = (
        "Você é um advogado brasileiro especialista. "
        "Responda de forma prática, assertiva e orientada à ação. "
        "Use APENAS o CONTEXTO fornecido (trechos dos PDFs ou web), "
        "sem citar nomes de PDFs ou URLs. "
        "NÃO diga que são 'orientações iniciais' ou peça contratação prévia. "
        "Estruture SEMPRE em: "
        "(1) Diagnóstico resumido; "
        "(2) O que fazer agora [passo a passo objetivo]; "
        "(3) Fundamentos legais aplicáveis; "
        "(4) Checklist de documentos; "
        "(5) Riscos e prazos; "
        "(6) Como atuaremos no caso; "
        "(7) Proposta inicial de honorários (faixa) e condições; "
        "(8) Próximos passos."
    )
    retriever_k: int = 6
    max_context_chars: int = 4500
    coverage_threshold: float = 0.30  # só cai para web se PDFs cobrirem pouco
    use_web: bool = True

def sane_reply(user_text: str, llm_reply: str, reprompt_fn):
    """Retorna resposta válida ou None após um re-prompt simples."""
    ut = (user_text or "").strip().lower()
    lr = (llm_reply or "").strip()
    if not lr or lr.lower() in {ut, "ok", "certo"}:
        llm_reply2 = reprompt_fn(
            f"Responda objetivamente em 4-6 linhas, com passos práticos. Pergunta: {user_text}"
        )
        if llm_reply2 and llm_reply2.strip().lower() != ut:
            return llm_reply2
        return None
    return lr

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
    
    # -------------------------------
    # Fallback temático determinístico
    # -------------------------------
    def _normalize_tema(self, tema: Optional[str]) -> str:
        t = (tema or "").strip().lower()
        if not t:
            return "geral"
        aliases = {
            "imobiliario": {"imobiliário", "locacao", "locação", "locaticio", "locatício", "despejo", "aluguel"},
            "familia": {"família", "familia", "divorcio", "divórcio", "guarda", "alimentos"},
            "consumidor": {"consumerista", "cdc", "compra", "produto", "serviço"},
            "trabalhista": {"trabalho", "empregado", "empregador", "clt", "justa causa"},
            "penal": {"criminal", "crime", "habeas corpus", "prisão"},
            "tributario": {"tributário", "fisco", "imposto", "refis"},
            "previdenciario": {"previdenciário", "inss", "beneficio", "aposentadoria"},
            "administrativo": {"licitação", "concurso", "ato administrativo", "ms", "mandado de segurança"},
            "empresarial": {"societário", "falência", "recuperação", "contratos empresariais"},
            "civel": {"civil", "responsabilidade civil", "indenização"},
            "processual_civil": {"processo civil", "cpc", "tutela", "execução", "cumprimento de sentença"},
        }
        for key, vals in aliases.items():
            if t == key or t in vals:
                return key
        # tenta “cair” para grupos amplos
        if "civil" in t:
            return "civel"
        return "geral"

    def _fallback_template_by_tema(self, tema_norm: str) -> dict:
        """
        Retorna blocos padrão por tema. Evite citar artigos/leis específicos aqui
        para não 'inventar' fundamento sem PDF/web. Use fundamentos genéricos seguros.
        """
        base = {
            "fundamentos": (
                "princípios aplicáveis (boa-fé, contraditório e ampla defesa, "
                "devido processo legal) e a legislação pertinente ao caso."
            ),
            "checklist": [
                "Documentos básicos (RG/CPF/Comprovante de endereço)",
                "Contrato/ato principal relacionado ao caso",
                "Comprovantes (pagamentos, mensagens, notificações, e-mails)",
                "Provas materiais (fotos, laudos, termos, boletins, etc.)",
            ],
            "riscos_prazos": (
                "Há prazos processuais e prescricionais relevantes. Quanto antes agirmos, "
                "maiores as chances de preservar direitos e evitar medidas desfavoráveis."
            ),
            "como_atuaremos": (
                "Análise documental pontual, definição de estratégia, preparação de peças e "
                "protocolos necessários; acompanhamento processual e comunicação contínua."
            ),
            "proposta": (
                "Honorários em faixa conforme complexidade e urgência, com opções de parcelamento. "
                "Emitimos contrato e recibos; trabalhamos com transparência de etapas e custos."
            ),
            "proximos_passos": (
                "Envie os documentos citados em PDF, confirmamos prazos críticos, alinhamos estratégia "
                "por escrito e encaminhamos contrato eletrônico para assinatura."
            ),
        }

        temas = {
            "imobiliario": {
                "o_que_fazer": [
                    "Separar notificação/carta recebida (preferencialmente com AR)",
                    "Reunir recibos/comprovantes de pagamento e extratos",
                    "Localizar contrato e eventuais aditivos",
                    "Preservar conversas com locador/administradora",
                ],
                "fundamentos": (
                    "boa-fé objetiva, adimplemento e regras da Lei do Inquilinato aplicáveis ao caso."
                ),
                "checklist_extra": ["Contrato de locação", "Comprovantes de aluguel/encargos", "Notificação (AR)"],
            },
            "familia": {
                "o_que_fazer": [
                    "Organizar certidões (casamento, nascimento, etc.)",
                    "Levantar realidade financeira (renda, despesas, dependentes)",
                    "Mapear fatos relevantes (guarda, convivência, violência, etc.)",
                ],
                "fundamentos": "melhor interesse do menor e normas de direito de família aplicáveis.",
                "checklist_extra": ["Certidões (casamento, nascimento)", "Comprovantes de renda/despesas"],
            },
            "consumidor": {
                "o_que_fazer": [
                    "Guardar notas fiscais, contratos e comunicações com a empresa",
                    "Registrar protocolo de atendimento",
                    "Reunir evidências do defeito/descumprimento (fotos, vídeos, laudos)",
                ],
                "fundamentos": "princípios do CDC (equilíbrio, informação, responsabilidade).",
                "checklist_extra": ["Nota/Contrato", "Protocolos", "Evidências do vício/defeito"],
            },
            "trabalhista": {
                "o_que_fazer": [
                    "Coletar holerites, CTPS e mensagens com RH/gestão",
                    "Anotar jornadas e eventuais horas extras",
                    "Reunir provas de assédio/irregularidades (se houver)",
                ],
                "fundamentos": "normas da CLT e entendimento jurisprudencial aplicável.",
                "checklist_extra": ["CTPS", "Holerites", "Comprovantes de jornada/comunicações"],
            },
            "penal": {
                "o_que_fazer": [
                    "Reunir boletins de ocorrência, decisões e despachos",
                    "Mapear risco de medidas cautelares e prazos",
                    "Identificar provas já produzidas e testemunhas-chave",
                ],
                "fundamentos": "devido processo, presunção de inocência e jurisprudência correlata.",
                "checklist_extra": ["BO/Autos", "Decisões", "Rol de testemunhas"],
            },
            "tributario": {
                "o_que_fazer": [
                    "Separar autos de infração, notificações e DARFs/GUIAs",
                    "Levantar histórico de apurações e pagamentos",
                    "Verificar programas de transação/refis vigentes",
                ],
                "fundamentos": "legalidade, capacidade contributiva e normas tributárias pertinentes.",
                "checklist_extra": ["Autos/Notificações", "Apurações/Comprovantes", "Provas contábeis"],
            },
            "previdenciario": {
                "o_que_fazer": [
                    "Coletar CNIS, PPP, laudos e exames (se aplicável)",
                    "Organizar histórico contributivo e vínculos",
                    "Verificar indeferimentos/recursos anteriores",
                ],
                "fundamentos": "normas previdenciárias aplicáveis e precedentes administrativos/judiciais.",
                "checklist_extra": ["CNIS", "PPP/Laudos", "Comprovantes de contribuições"],
            },
            "administrativo": {
                "o_que_fazer": [
                    "Reunir edital/ato administrativo e publicações",
                    "Guardar protocolos/impugnações já feitas",
                    "Mapear prazos de recurso/impugnação",
                ],
                "fundamentos": "legalidade, impessoalidade e controle de atos administrativos.",
                "checklist_extra": ["Edital/Ato", "Protocolos", "Comprovantes de prazos"],
            },
            "empresarial": {
                "o_que_fazer": [
                    "Separar contratos sociais/atos societários",
                    "Organizar contratos com clientes/fornecedores",
                    "Levantar passivos e contingências",
                ],
                "fundamentos": "normas societárias/empresariais e pacta sunt servanda.",
                "checklist_extra": ["Contrato social/alterações", "Contratos relevantes", "Demonstrações financeiras"],
            },
            "civel": {
                "o_que_fazer": [
                    "Reunir contrato/ato-base e provas do fato",
                    "Quantificar danos/valores envolvidos",
                    "Listar testemunhas e comunicações relevantes",
                ],
                "fundamentos": "responsabilidade civil e princípios contratuais.",
                "checklist_extra": ["Contrato/Provas", "Cálculo de danos", "Mensagens/e-mails"],
            },
            "processual_civil": {
                "o_que_fazer": [
                    "Identificar fase do processo (inicial, tutela, execução)",
                    "Checar prazos em curso (dias úteis)",
                    "Separar cópias das peças e decisões",
                ],
                "fundamentos": "regras do CPC aplicáveis à fase e ao pedido.",
                "checklist_extra": ["Peças/Decisões", "Comprovantes de intimação", "Cálculos/Planilhas"],
            },
            "geral": {
                "o_que_fazer": [
                    "Organizar fatos em ordem cronológica",
                    "Reunir o documento/ato principal e evidências",
                    "Identificar prazos e valores envolvidos",
                ],
                "fundamentos": base["fundamentos"],
                "checklist_extra": [],
            },
        }

        t = temas.get(tema_norm, temas["geral"])
        return {
            "o_que_fazer": t["o_que_fazer"],
            "fundamentos": t["fundamentos"],
            "checklist": base["checklist"] + t.get("checklist_extra", []),
            "riscos_prazos": base["riscos_prazos"],
            "como_atuaremos": base["como_atuaremos"],
            "proposta": base["proposta"],
            "proximos_passos": base["proximos_passos"],
        }

    def _build_fallback_answer(self, user_text: str, tema: Optional[str]) -> str:
        tema_norm = self._normalize_tema(tema)
        t = self._fallback_template_by_tema(tema_norm)
        # Montagem padronizada (SEM "orientação preliminar...")
        linhas = []
        linhas.append(f"Diagnóstico: com base no relato, trata-se de tema {tema_norm.replace('_', ' ')}.")
        linhas.append("O que fazer agora:")
        for i, passo in enumerate(t["o_que_fazer"], 1):
            linhas.append(f"{i}) {passo}")
        linhas.append(f"Fundamentos: {t['fundamentos']}")
        linhas.append("Checklist de documentos:")
        for doc in t["checklist"]:
            linhas.append(f"- {doc}")
        linhas.append(f"Riscos e prazos: {t['riscos_prazos']}")
        linhas.append(f"Como atuaremos: {t['como_atuaremos']}")
        linhas.append(f"Proposta (faixa/condições): {t['proposta']}")
        linhas.append(f"Próximos passos: {t['proximos_passos']}")
        return "\n".join(linhas)

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
    
    def _chunk_text(self, c: Any) -> str:
        if isinstance(c, dict):
            return c.get("text") or c.get("chunk") or ""
        return getattr(c, "text", "") or str(c)

    def _chunk_source(self, c: Any) -> Optional[str]:
        if isinstance(c, dict):
            return c.get("source") or c.get("metadata", {}).get("source")
        return getattr(c, "source", None) or getattr(c, "metadata", {}).get("source")


    def _safe_web_search(self, query: str) -> str:
        logging.info(
            "WEB FALLBACK: use_web=%s, tavily=%s",
            self.conf.use_web,
            bool(getattr(self, "tavily", None)),
        )
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
        logging.info(
            "RAG: chunks=%d, coverage=%.2f, use_web=%s, tavily=%s",
            len(chunks),
            coverage,
            self.conf.use_web,
            bool(getattr(self, "tavily", None)),
        )
        for i, c in enumerate(chunks[:3]):
            src = getattr(c, "source", None) or getattr(c, "metadata", {}).get("source")
            logging.info("RAG chunk %d fonte=%s", i + 1, src)
        web_ctx = ""
        if coverage < self.conf.coverage_threshold:
            web_ctx = self._safe_web_search(user_text)

        parts = [p for p in (pdf_ctx, web_ctx) if p]
        context = ("\n\n".join(parts))[: self.conf.max_context_chars]
        if context:
            prompt = (
                f"PERGUNTA: {user_text}\n\n"
                "INSTRUÇÕES:\n"
                "- Responda como advogado brasileiro especialista.\n"
                "- Siga o formato: (1) Diagnóstico; (2) O que fazer agora; "
                "(3) Fundamentos; (4) Checklist; (5) Riscos e prazos; "
                "(6) Como atuaremos; (7) Proposta (faixa/condições); (8) Próximos passos.\n"
                "- Não repita a pergunta. Não diga que são orientações iniciais.\n"
                "- Use apenas o CONTEXTO abaixo, sem citar nomes de PDFs/URLs.\n\n"
                f"CONTEXTO:\n{context}"
            )
        else:
            prompt = (
                f"PERGUNTA: {user_text}\n\n"
                "INSTRUÇÕES:\n"
                "- Mesmo sem contexto, responda de forma objetiva e juridicamente segura.\n"
                "- Siga o formato: (1) Diagnóstico; (2) O que fazer agora; (3) Fundamentos; "
                "(4) Checklist; (5) Riscos e prazos; (6) Como atuaremos; "
                "(7) Proposta (faixa/condições); (8) Próximos passos.\n"
                "- Não diga que são orientações iniciais.\n"
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

        def _reprompt(u: str) -> str:
            if hasattr(self.llm, "generate"):
                try:
                    return self.llm.generate(
                        [
                            {
                                "role": "system",
                                 "content": "Você é um advogado brasileiro. Responda objetivamente em 4-6 linhas.",
                            },
                            {"role": "user", "content": user_text},
                        ],
                        temperature=0.2,
                        max_tokens=700,
                    )
                except Exception:
                    logging.exception("Retry do LLM falhou.")
            return ""
        raw = sane_reply(user_text, raw, _reprompt)
        if raw is None:
            logging.warning("LLM vazio/eco — usando fallback temático.")
            raw = self._build_fallback_answer(user_text, tema)
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
    logging.getLogger(__name__).info("LLM selecionado: %s", type(llm).__name__)
    if type(llm).__name__ in {"_StubLLM", "LLMStub"}:
        raise RuntimeError(
            "LLM real não inicializado. Verifique OPENAI_API_KEY/OPENAI_MODEL e o pacote 'openai'."
        )
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

