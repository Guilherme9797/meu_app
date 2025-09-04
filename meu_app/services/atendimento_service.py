from __future__ import annotations
import logging, re
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from .refinador import GroundingGuard, RefinadorResposta

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
    greeting_mode: str = "deterministic"  # "deterministic" | "llm"
    min_rag_chunks: int = 2
    force_topic_llm_on_ambiguous: bool = False
    avoid_generic_fallback: bool = False
    default_fallback_tema: str = ""

# --- helpers para "pseudo-chunks" ---
class _Chunk:
    def __init__(self, text: str, source: str = None, metadata: dict | None = None):
        self.text = text
        self.source = source
        self.metadata = metadata or {}



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
        refinador: Any = None,
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
        self.refinador = refinador
        self.conf = conf or AtendimentoConfig()
        self.conf.greeting_mode = getattr(self.conf, "greeting_mode", "deterministic")
    
    def _gen(self, messages, max_new: int = 900, temperature: Optional[float] = None) -> str:
        """Wrapper resiliente para self.llm.generate."""
        attempts = [
            {"max_completion_tokens": max_new, "temperature": temperature},
            {"max_tokens": max_new, "temperature": temperature},
            {"max_tokens": max_new},
            {},
        ]
        for params in attempts:
            params = {k: v for k, v in params.items() if v is not None}
            try:
                return self.llm.generate(messages, **params)
            except TypeError:
                continue
            except Exception as e:
                s = str(e).lower()
                if any(x in s for x in ["unsupported", "max_tokens", "max_completion_tokens", "temperature"]):
                    continue
                logging.exception("LLM.generate falhou de forma não tratável.")
                break
        return ""

    # ------------------------------------------------------------------
    # Helpers de classificação
    # ------------------------------------------------------------------
    def _infer_default_tema(self, text: str) -> str:
        """Heurística simples para tema padrão."""
        return "geral"
    
    def _is_greeting_only(self, text: str) -> bool:
        # Cumprimento curto (≤ 4 palavras), tem palavra de cumprimento,
        # não tem gatilho de caso e é “baixo sinal”.
        t = (text or "").strip().lower()
        if (
            len(t.split()) <= 4
            and self._has_greeting_word(t)
            and not self._has_case_intent(t)
            and self._is_low_signal_query(t)
        ):
            return True
        return False

    def _has_greeting_word(self, t: str) -> bool:
        t = (t or "").lower()
        greetings = ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "hello", "hi"]
        return any(g in t for g in greetings)

    def _has_case_intent(self, t: str) -> bool:
        t = (t or "").lower()
        gatilhos = [
            "preciso",
            "tenho",
            "tive",
            "quero",
            "não reconheço",
            "nao reconheco",
            "problema",
            "negativa",
            "negativ",
            "multa",
            "transfer",
            "processo",
            "despejo",
            "divórcio",
            "divorcio",
            "janela",
            "vizinh",
            "cobrança",
            "cobranca",
        ]
        return any(g in t for g in gatilhos)
    
    def _is_greeting_medium(self, text: str) -> bool:
        t = (text or "").strip().lower()
        # Cumprimento com um pouquinho mais de “encheção”,
        # mas ainda sem sinal de caso.
        if self._has_greeting_word(t) and not self._has_case_intent(t) and self._is_low_signal_query(t):
            return True
        return False

    def _greeting_reply(self) -> str:
        return (
            "Olá! Como posso ajudar? "
            "Para eu orientar melhor, me diga em 1 frase: (i) o tema (ex.: consumidor, família, penal...), "
            "(ii) se há prazo urgente, e (iii) quais documentos você tem em mãos."
        )

    def _llm_smalltalk(self, user_text: str) -> str:
        sys = (
            "Você é um advogado brasileiro cordial. "
            "Responda em 1 linha, acolhedor, SEM conteúdo jurídico. "
            "Finalize com UMA pergunta de triagem (tema, prazo, documentos). "
            "Máx ~60 tokens."
        )
        msgs = [
            {"role": "system", "content": sys},
            {"role": "user", "content": user_text},
        ]
        try:
            if hasattr(self.llm, "generate"):
                try:
                    return self.llm.generate(msgs, max_completion_tokens=60) or self._greeting_reply()
                except TypeError:
                    try:
                        return self.llm.generate(msgs, max_tokens=60) or self._greeting_reply()
                    except TypeError:
                        return self.llm.generate(msgs) or self._greeting_reply()
        except Exception:
            logging.exception("smalltalk falhou")
        return self._greeting_reply()

    def _is_low_signal_query(self, text: str) -> bool:
        words = re.findall(r"\w+", (text or "").lower(), flags=re.UNICODE)
        if len(words) <= 2:
            return True
        fillers = {"oi", "olá", "ola", "bom", "dia", "boa", "tarde", "noite", "tudo", "bem", "como", "vai", "e", "ai", "aí"}
        content = [w for w in words if w not in fillers]
        return len(content) < 2

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
    def _infer_tema_from_text(self, text: str) -> Optional[str]:
        t = (text or "").lower()
        # honra/difamação → cível_honra
        if any(k in t for k in ["difama", "injúria", "injuria", "calúnia", "calunia", "honra", "caloteiro", "exposição", "exposicao", "xingamento"]):
            return "civel_honra"
        # negativação/consumidor
        if any(k in t for k in ["serasa", "spc", "negativa", "negativação", "negativacao", "cobrança", "cobranca"]):
            return "consumidor"
        # locação/despejo
        if any(k in t for k in ["aluguel", "despejo", "locação", "locacao", "locador", "locatário", "locatario"]):
            return "imobiliario"
        return None

    def _infer_tema_from_chunks(self, chunks: List[Any]) -> Optional[str]:
        if not chunks:
            return None
        # junta possíveis fontes
        srcs = []
        for c in chunks:
            s1 = getattr(c, "source", "") or ""
            md = getattr(c, "metadata", {}) or {}
            s2 = md.get("source", "")
            srcs.append(str(s1).lower())
            srcs.append(str(s2).lower())
        blob = " ".join(srcs)

        mapping = [
            ("civel_honra", ["civil", "civel"]),   # honra costuma vir do civil
            ("consumidor",  ["cdc", "consumidor"]),
            ("imobiliario", ["inquilin", "loca", "imobili"]),
            ("penal",       ["penal_especial", "penal", "criminologia"]),
            ("tributario",  ["tributario"]),
            ("previdenciario", ["previdenciario"]),
            ("administrativo", ["administrativo"]),
            ("processual_civil", ["processual civil", "cpc"]),
            ("civel", ["civil", "civel"]),
        ]
        for tema, keys in mapping:
            if any(k in blob for k in keys):
                return tema
        return None

    def _guess_topic_llm(self, text: str) -> Optional[str]:
        prompt = (
            "Aponte em uma palavra o tema jurídico principal da pergunta a seguir "
            "(ex.: consumidor, trabalhista, penal, civel, familia)."
        )
        try:
            out = self._gen(
                [{"role": "user", "content": f"{prompt}\n\nPergunta: {text}"}],
                max_new=20,
            )
        except Exception:
            return None
        parts = (out or "").strip().lower().split()
        return parts[0] if parts else None

    def _choose_fallback_tema(self, user_text: str, chunks: List[Any]) -> Optional[str]:
        tema = self._infer_tema_from_text(user_text) or self._infer_tema_from_chunks(chunks)
        if (not tema or tema == "geral") and not self._is_low_signal_query(user_text):
            if getattr(self.conf, "force_topic_llm_on_ambiguous", False):
                tema = self._guess_topic_llm(user_text) or tema
            if (
                not tema or tema == "geral"
            ) and getattr(self.conf, "avoid_generic_fallback", False):
                tema = getattr(self.conf, "default_fallback_tema", "civel")
        return tema
    
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
             "civel": {"civil", "responsabilidade civil", "indenização", "civel_honra"},
            "processual_civil": {"processo civil", "cpc", "tutela", "execução", "cumprimento de sentença"},
        }
        for key, vals in aliases.items():
            if t == key or t in vals:
                return key
        # tenta “cair” para grupos amplos
        if "civil" in t or "civel" in t:
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
    # Nova arquitetura: CaseFrame, multi-retrieve e geração com fontes
    # ------------------------------------------------------------------

    def _caseframe_extract(self, text: str) -> dict:
        """Extrai um quadro estruturado do caso (fatos, objetivo, tags...)."""
        prompt = (
            "Leia a pergunta do cliente e devolva um JSON com campos:\n"
            "{facts: string curto, goal: string curto, parties: [string], "
            "values: [string], deadlines: [string], tags: [string]}\n"
            "Se não souber um campo, deixe vazio. Não invente.\n"
            f"Pergunta: {text}"
        )
        try:
            if hasattr(self.llm, "generate"):
                out = self._gen([{"role": "user", "content": prompt}], max_new=400)
            else:
                out = ""
        except Exception:
            logging.exception("Frame extract falhou.")
            out = ""
        import json as _json
        default = {
            "facts": "",
            "goal": "",
            "parties": [],
            "values": [],
            "deadlines": [],
            "tags": [],
        }
        try:
            data = _json.loads(out) if isinstance(out, str) else default
            if not isinstance(data, dict):
                data = default
        except Exception:
            data = default
        return data

    def _expand_queries(self, user_text: str, frame: dict) -> List[str]:
        tags = frame.get("tags") or []
        facts = (frame.get("facts") or "")[:180]
        goal = (frame.get("goal") or "")[:120]
        q: List[str] = [user_text]
        if facts:
            q.append(facts)
        if goal:
            q.append(goal)
        for t in tags[:5]:
            q.append(f"{t} {user_text}")
        q.append(f"disputa: {facts or user_text}")
        return [s for s in q if s and len(s) > 3]

    def _query_rewrite(self, text: str) -> List[str]:
        p = (
            "Gere 3 a 5 consultas curtas (máx 6 palavras) sobre o caso, uma por linha, "
            "sem pontuação, visando recuperação de trechos jurídicos úteis."
        )
        try:
            out = self._gen(
                [{"role": "user", "content": f"{p}\n\nCaso: {text}"}], max_new=80
            )
        except Exception:
            out = ""
        qs = [q.strip("•- ").lower() for q in (out or "").splitlines() if q.strip()]
        return qs[:5]
    
    def _split_ctx_as_chunks(self, ctx: str, max_chars: int = 450, max_chunks: int = 6) -> list[_Chunk]:
        import re
        out: list[_Chunk] = []
        if not ctx:
            return out
        blocks = re.split(r"\n{2,}", ctx) or [ctx]
        for b in blocks:
            s = (b or "").strip()
            if not s:
                continue
            if len(s) > max_chars:
                parts = re.split(r"(?<=[\.\!\?])\s+", s)
                cur = ""
                for p in parts:
                    if not p:
                        continue
                    if len(cur) + len(p) + 1 <= max_chars:
                        cur = (cur + " " + p).strip()
                    else:
                        if cur:
                            out.append(_Chunk(cur, source="pdf_ctx"))
                        cur = p
                if cur:
                    out.append(_Chunk(cur, source="pdf_ctx"))
            else:
                out.append(_Chunk(s, source="pdf_ctx"))
            if len(out) >= max_chunks:
                break
        return out

    def _retrieve_any(self, query: str, k: int) -> List[Any]:
        r = self.retriever
        try:
            if hasattr(r, "retrieve"):
                return list(r.retrieve(query, k=k))
            if hasattr(r, "buscar_chunks"):
                return list(r.buscar_chunks(query, k=k))
            if hasattr(r, "buscar_contexto"):
                ctx = r.buscar_contexto(query, k=k)
                return self._split_ctx_as_chunks(ctx, max_chars=450, max_chunks=k)
            if hasattr(r, "search"):
                res = r.search(query, k=k)
                if isinstance(res, str):
                    return self._split_ctx_as_chunks(res, max_chars=450, max_chunks=k)
                if isinstance(res, list):
                    return [_Chunk(getattr(x, "text", str(x))) for x in res[:k]]
        except Exception:
            logging.exception("Falha na recuperação (adapter).")
        return []
    
    def _retrieve_multi(self, queries: List[str], k: int = 6) -> List[Any]:
        """Executa múltiplas recuperações e combina resultados (RRF + MMR)."""
        from collections import defaultdict

        ranked = defaultdict(float)
        pools = []
        for q in queries[:6]:
            results = self._retrieve_any(q, k=k)
            pools.append(results)
            for i, ch in enumerate(results):
                ranked[id(ch)] += 1.0 / (i + 1.0)

        all_items = {id(c): c for pool in pools for c in pool}
        candidates = sorted(
            all_items.values(), key=lambda c: ranked.get(id(c), 0), reverse=True
        )

        def _sim(a: str, b: str) -> float:
            a, b = (a or "")[:400], (b or "")[:400]
            if not a or not b:
                return 0.0
            inter = len(set(a.split()) & set(b.split()))
            return inter / float(1 + min(len(a.split()), len(b.split())))

        picked: List[Any] = []
        for c in candidates:
            txt = getattr(c, "text", str(c)) or ""
            if not picked:
                picked.append(c)
                continue
            if all(_sim(txt, getattr(p, "text", str(p))) < 0.6 for p in picked):
                picked.append(c)
            if len(picked) >= k:
                break
        return picked

    def _build_source_pack(self, chunks: List[Any]) -> str:
        """Cria pacote numerado S1..Sn com micro-resumos e trechos."""
        pack: List[str] = []
        total = 0
        limit = self.conf.max_context_chars
        for i, c in enumerate(chunks, 1):
            txt = (getattr(c, "text", str(c)) or "").strip()
            snippet = txt[:450]
            resume = snippet.split(". ")[0][:200]
            entry = f"[S{i}] {resume}.\nTrecho: {snippet}"
            total += len(entry)
            if total > limit:
                break
            pack.append(entry)
        return "\n\n".join(pack)

    def _answer_from_sources(self, user_text: str, source_pack: str) -> str:
        system = self.conf.system_prompt
        user = (
            f"PERGUNTA: {user_text}\n\n"
            "USE E CITE obrigatoriamente os S# do SOURCE PACK. Se algo não estiver nos S#, peça o documento/dado específico em 1 linha.\n"
            "Formato fixo: (1) Diagnóstico; (2) O que fazer agora (passo a passo prático); (3) Fundamentos (referencie S#); (4) Checklist; (5) Riscos/prazos; (6) Como atuaremos; (7) Proposta (faixa/condições); (8) Próximos passos.\n\n"
            f"SOURCE PACK:\n{source_pack}"
        )
        try:
            return self._gen(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_new=900,
            )
        except Exception:
            logging.exception("Falha no gerador com fontes.")
            return ""

    def _guard_check(self, text: str) -> bool:
        try:
            if hasattr(self.guard, "check"):
                g = self.guard.check(text)
                if isinstance(g, dict):
                    return bool(g.get("allowed", True))
        except Exception:
            logging.exception("Falha no Guard.")
        return True

    # ------------------------------------------------------------------
    # Recuperação e web
    # ------------------------------------------------------------------
    def _safe_retrieve(self, query: str, tema: Optional[str] = None, ents: Optional[List[str]] = None) -> List[Any]:
        try:
            return self._retrieve_any(query, k=self.conf.retriever_k)
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
        """Orquestra a resposta usando CaseFrame, RAG multi e guard."""
        if self._is_greeting_only(user_text):
            return (
                self._llm_smalltalk(user_text)
                if self.conf.greeting_mode == "llm"
                else self._greeting_reply()
            )

        if self._is_greeting_medium(user_text) and self.conf.greeting_mode == "llm":
            return self._llm_smalltalk(user_text)
        if not self._guard_check(user_text):
            return "No momento não posso atender a esse pedido."

        frame = self._caseframe_extract(user_text)
        queries = self._expand_queries(user_text, frame)
        logging.info("queries=%s", queries[:4])
        chunks = self._retrieve_multi(queries, k=self.conf.retriever_k)
        if len(chunks) < self.conf.min_rag_chunks:
            rewrites = self._query_rewrite(user_text)
            if rewrites:
                chunks2 = self._retrieve_multi(
                    rewrites + queries[:2], k=self.conf.retriever_k
                )
                if len(chunks2) > len(chunks):
                    chunks = chunks2
        coverage = self._score_pdf_coverage(chunks)
        logging.info(
             "RAG multi: q=%d chunks=%d coverage=%.2f", len(queries), len(chunks), coverage
        )
        web_ctx = ""
        if coverage < self.conf.coverage_threshold and not self._is_low_signal_query(user_text):
            tags = " ".join((frame.get("tags") or [])[:3])
            web_ctx = self._safe_web_search(f"{user_text} {tags}".strip())
            if web_ctx:
                chunks = chunks + [type("WebChunk", (object,), {"text": web_ctx})()]

        src_pack = ""
        if chunks:
            src_pack = self._build_source_pack(chunks)
            src_pack = src_pack[: self.conf.max_context_chars]
            logging.info(
                "source_pack_preview=%s", src_pack[:200].replace("\n", " ")
            )
            answer = self._answer_from_sources(user_text, src_pack)
        else:
            answer = ""
        if not answer:
            tema_fb = self._choose_fallback_tema(user_text, chunks)
            answer = self._build_fallback_answer(user_text, tema_fb)
        answer = sane_reply(
            user_text,
            answer,
            reprompt_fn=lambda p: self._gen([{"role": "user", "content": p}], max_new=160),
        ) or answer
        _has_sref = bool(re.search(r"\[S\d+\]", answer or ""))
        if chunks and not _has_sref and src_pack:
            logging.info("Re-prompting to include source references.")
            reprompt = (
                "Reescreva a resposta a seguir citando obrigatoriamente os S# do SOURCE PACK.\n\n"
                f"PERGUNTA: {user_text}\n\nRESPOSTA: {answer}\n\nSOURCE PACK:\n{src_pack}"
            )
            answer2 = self._gen(
                [
                    {"role": "system", "content": self.conf.system_prompt},
                    {"role": "user", "content": reprompt},
                ],
                max_new=900,
            )
            if answer2:
                answer = answer2
            _has_sref = bool(re.search(r"\[S\d+\]", answer or ""))
        if not self._guard_check(answer):
            logging.warning("Saída reprovada no guard — usando fallback seguro.")
            tema_fb = self._choose_fallback_tema(user_text, chunks)
            answer = self._build_fallback_answer(user_text, tema_fb)
        elif chunks and not _has_sref:
            logging.warning("Saída sem [S#]; inserindo referência mínima.")
            answer = f"{answer.strip()} [S1]"
        
        if self.refinador:
            try:
                answer = self.refinador.refinar(answer)
            except Exception:
                logging.exception("Falha no refinador.")

        return answer

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

    # Tenta construir o buscador real baseado em FAISS. Em ambientes de teste
    # ou sem dependências, recai para um stub que apenas retorna listas vazias.
    retriever: Any
    try:
        from .buscador_pdf import BuscadorPDF
        buscador = BuscadorPDF(
            openai_key=os.getenv("OPENAI_API_KEY", ""),
            tavily_key=os.getenv("TAVILY_API_KEY"),
            pdf_dir=os.getenv("PDFS_DIR", "data/pdfs"),
            index_dir=get_index_dir(),
        )
        # Passamos o objeto BuscadorPDF diretamente para aproveitar o método
        # ``buscar_contexto`` já suportado por AtendimentoService.
        retriever = buscador
    except Exception as e:  # pragma: no cover - defensivo
        logging.exception("Falha ao inicializar BuscadorPDF: %s", e)
        class RetrieverStub:
            def retrieve(self, query: str, k: int = 4) -> List[Any]:
                return []

            def buscar_contexto(self, consulta: str, k: int = 5) -> str:
                return ""

        retriever = RetrieverStub()

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

    class Classifier:
        pass

    class Extractor:
        pass

    class SessionRepository:
        pass

    class MessageRepository:
        pass

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
    refinador = RefinadorResposta(llm)
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
        refinador=refinador,
        conf=conf,
    
    )

