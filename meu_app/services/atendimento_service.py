from __future__ import annotations
import logging, re
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from .refinador import GroundingGuard, RefinadorResposta
from .analisador import _norm_txt, _iter_ontology_paths, _get_node_by_path, _CPC_ONTOLOGY
from .penal_ontology import _PENAL_ONTOLOGY
from .proc_penal_ontology import _PROC_PENAL_ONTOLOGY
from .tributario_ontology import _TRIBUTARIO_ONTOLOGY
from .empresarial_ontology import _EMPRESARIAL_ONTOLOGY
from .previdenciario_ontology import _PREVID_ONTOLOGY
from .ambiental_ontology import _AMBIENTAL_ONTOLOGY
from meu_app.retrievers.datajud import (
    DatajudClient,
    DatajudRetriever,
    CombinedRetriever,
)
from meu_app.retrievers.web_tavily import WebRetriever
from meu_app.retrievers.query_expander import expand as expand_query
from meu_app.providers.bnp_provider import BNPProvider
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
    min_rag_chunks: int = 2                  # se <2, tenta query rewrite
    force_topic_llm_on_ambiguous: bool = True
    avoid_generic_fallback: bool = True      # não usar 'geral' se houver sinal
    default_fallback_tema: str = "civel"     # tema mínimo aceitável

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
        self.bnp = BNPProvider(tavily)
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
    
    # ---------------------------------------------------------
    # CPC: detecção por ontologia (estrutura reduzida)
    # ---------------------------------------------------------
    def _cpc_detect_paths(self, user_text: str, max_hits: int = 8) -> list[str]:
        t = _norm_txt(user_text)
        paths = _iter_ontology_paths(_CPC_ONTOLOGY)
        hits = []
        for path, label in paths:
            if label and label in t and path not in hits:
                hits.append(path)
                if len(hits) >= max_hits:
                    break
        return hits

    def _cpc_tags_from_paths(self, paths: list[str]) -> list[str]:
        tags = []
        for p in paths:
            leaf = p.split(".")[-1]
            tags.append(f"cpc_{leaf}")
        seen, out = set(), []
        for tg in tags:
            if tg not in seen:
                seen.add(tg)
                out.append(tg)
        return out[:12]

    def _cpc_hints(self, paths_or_tags: list[str], max_hints: int = 10) -> list[str]:
        hints: list[str] = []
        for key in paths_or_tags[:6]:
            if key.startswith("cpc_"):
                leaf = key[len("cpc_"):]
                for p, _ in _iter_ontology_paths(_CPC_ONTOLOGY):
                    if p.endswith("." + leaf) or p == leaf:
                        node = _get_node_by_path(_CPC_ONTOLOGY, p)
                        break
                else:
                    node = None
            else:
                node = _get_node_by_path(_CPC_ONTOLOGY, key)
            if node is None:
                continue
            if isinstance(node, list):
                items = node
            elif isinstance(node, dict):
                items = list(node.keys())
            else:
                items = [str(node)]
            for it in items:
                h = _norm_txt(str(it))
                if h and h not in hints:
                    hints.append(h)
                if len(hints) >= max_hints:
                    return hints
        return hints

    def _maybe_add_cpc_macro(self, tags: list[str], cpc_paths: list[str]) -> list[str]:
        macro = "processual_civil"
        if cpc_paths and macro not in tags:
            tags = tags + [macro]
        return tags

    # ---------------------------------------------------------
    # PENAL: detecção por ontologia
    # ---------------------------------------------------------
    def _penal_detect_paths(self, user_text: str, max_hits: int = 8) -> list[str]:
        t = _norm_txt(user_text)
        paths = _iter_ontology_paths(_PENAL_ONTOLOGY)
        hits = []
        for path, label in paths:
            if label and label in t and path not in hits:
                hits.append(path)
                if len(hits) >= max_hits:
                    break
        return hits

    def _penal_tags_from_paths(self, paths: list[str]) -> list[str]:
        tags = []
        for p in paths:
            leaf = p.split(".")[-1]
            tags.append(f"penal_{leaf}")
        seen, out = set(), []
        for tg in tags:
            if tg not in seen:
                seen.add(tg)
                out.append(tg)
        return out[:12]

    def _penal_hints(self, paths_or_tags: list[str], max_hints: int = 10) -> list[str]:
        hints: list[str] = []
        for key in paths_or_tags[:6]:
            if key.startswith("penal_"):
                leaf = key[len("penal_"):]
                for p, _ in _iter_ontology_paths(_PENAL_ONTOLOGY):
                    if p.endswith("." + leaf) or p == leaf:
                        node = _get_node_by_path(_PENAL_ONTOLOGY, p)
                        break
                else:
                    node = None
            else:
                node = _get_node_by_path(_PENAL_ONTOLOGY, key)
            if node is None:
                continue
            if isinstance(node, list):
                items = node
            elif isinstance(node, dict):
                items = list(node.keys())
            else:
                items = [str(node)]
            for it in items:
                h = _norm_txt(str(it))
                if h and h not in hints:
                    hints.append(h)
                if len(hints) >= max_hints:
                    return hints
        return hints

    def _maybe_add_penal_macro(self, tags: list[str], penal_paths: list[str]) -> list[str]:
        macro = "direito_penal"
        if penal_paths and macro not in tags:
            tags = tags + [macro]
        return tags
    
    # ---------------------------------------------------------
    # DPP (Direito Processual Penal): detecção por ontologia
    # ---------------------------------------------------------
    def _dpp_detect_paths(self, user_text: str, max_hits: int = 8) -> list[str]:
        t = _norm_txt(user_text)
        paths = _iter_ontology_paths(_PROC_PENAL_ONTOLOGY)
        hits: list[str] = []
        for path, label in paths:
            if label and label in t and path not in hits:
                hits.append(path)
                if len(hits) >= max_hits:
                    break
        return hits

    def _dpp_tags_from_paths(self, paths: list[str]) -> list[str]:
        tags: list[str] = []
        for p in paths:
            leaf = p.split(".")[-1]
            tags.append(f"dpp_{leaf}")
        # dedup
        seen, out = set(), []
        for tg in tags:
            if tg not in seen:
                seen.add(tg)
                out.append(tg)
        return out[:12]

    def _dpp_hints(self, paths_or_tags: list[str], max_hints: int = 10) -> list[str]:
        hints: list[str] = []
        for key in paths_or_tags[:6]:
            if key.startswith("dpp_"):
                leaf = key[len("dpp_"):]
                for p, _ in _iter_ontology_paths(_PROC_PENAL_ONTOLOGY):
                    if p.endswith("." + leaf) or p == leaf:
                        node = _get_node_by_path(_PROC_PENAL_ONTOLOGY, p)
                        break
                else:
                    node = None
            else:
                node = _get_node_by_path(_PROC_PENAL_ONTOLOGY, key)

            if node is None:
                continue
            items = (
                node
                if isinstance(node, list)
                else (list(node.keys()) if isinstance(node, dict) else [str(node)])
            )
            for it in items:
                h = _norm_txt(str(it))
                if h and h not in hints:
                    hints.append(h)
                if len(hints) >= max_hints:
                    return hints
        return hints

    def _maybe_add_dpp_macro(self, tags: list[str], dpp_paths: list[str]) -> list[str]:
        macro = "direito_processual_penal"
        if dpp_paths and macro not in tags:
            tags = tags + [macro]
        return tags

    # ---------------------------------------------------------
    # TRIBUTÁRIO: detecção por ontologia → tags → hints
    # ---------------------------------------------------------
    def _trib_detect_paths(self, user_text: str, max_hits: int = 10) -> list[str]:
        t = _norm_txt(user_text)
        hits: list[str] = []
        for path, label in _iter_ontology_paths(_TRIBUTARIO_ONTOLOGY):
            if label and label in t and path not in hits:
                hits.append(path)
                if len(hits) >= max_hits:
                    break
        return hits

    def _trib_tags_from_paths(self, paths: list[str]) -> list[str]:
        tags: list[str] = []
        for p in paths:
            leaf = p.split(".")[-1]
            tags.append(f"trib_{leaf}")
        # dedup e limite
        seen, out = set(), []
        for tg in tags:
            if tg not in seen:
                seen.add(tg)
                out.append(tg)
        return out[:16]

    def _trib_hints(self, paths_or_tags: list[str], max_hints: int = 10) -> list[str]:
        hints: list[str] = []
        for key in paths_or_tags[:8]:
            node = None
            if key.startswith("trib_"):
                leaf = key[len("trib_"):]
                for p, _ in _iter_ontology_paths(_TRIBUTARIO_ONTOLOGY):
                    if p.endswith("." + leaf) or p == leaf:
                        node = _get_node_by_path(_TRIBUTARIO_ONTOLOGY, p)
                        break
            else:
                node = _get_node_by_path(_TRIBUTARIO_ONTOLOGY, key)

            if node is None:
                continue
            items = (
                node
                if isinstance(node, list)
                else (list(node.keys()) if isinstance(node, dict) else [str(node)])
            )
            for it in items:
                h = _norm_txt(str(it))
                if h and h not in hints:
                    hints.append(h)
                if len(hints) >= max_hints:
                    return hints
        return hints

    def _maybe_add_trib_macro(self, tags: list[str], trib_paths: list[str]) -> list[str]:
        macro = "direito_tributario"
        if trib_paths and macro not in tags:
            tags = tags + [macro]
        return tags

    # ---------------------------------------------------------
    # EMPRESARIAL: detecção por ontologia → tags → hints
    # ---------------------------------------------------------
    def _emp_detect_paths(self, user_text: str, max_hits: int = 10) -> list[str]:
        t = _norm_txt(user_text)
        hits: list[str] = []
        for path, label in _iter_ontology_paths(_EMPRESARIAL_ONTOLOGY):
            if label and label in t and path not in hits:
                hits.append(path)
                if len(hits) >= max_hits:
                    break
        return hits

    def _emp_tags_from_paths(self, paths: list[str]) -> list[str]:
        tags: list[str] = []
        for p in paths:
            leaf = p.split(".")[-1]
            tags.append(f"emp_{leaf}")
        # dedup + limite
        seen, out = set(), []
        for tg in tags:
            if tg not in seen:
                seen.add(tg)
                out.append(tg)
        return out[:16]

    def _emp_hints(self, paths_or_tags: list[str], max_hints: int = 10) -> list[str]:
        hints: list[str] = []
        for key in paths_or_tags[:8]:
            node = None
            if key.startswith("emp_"):
                leaf = key[len("emp_"):]
                for p, _ in _iter_ontology_paths(_EMPRESARIAL_ONTOLOGY):
                    if p.endswith("." + leaf) or p == leaf:
                        node = _get_node_by_path(_EMPRESARIAL_ONTOLOGY, p)
                        break
            else:
                node = _get_node_by_path(_EMPRESARIAL_ONTOLOGY, key)

            if node is None:
                continue
            items = node if isinstance(node, list) else (list(node.keys()) if isinstance(node, dict) else [str(node)])
            for it in items:
                h = _norm_txt(str(it))
                if h and h not in hints:
                    hints.append(h)
                if len(hints) >= max_hints:
                    return hints
        return hints

    def _maybe_add_emp_macro(self, tags: list[str], emp_paths: list[str]) -> list[str]:
        macro = "direito_empresarial"
        if emp_paths and macro not in tags:
            tags = tags + [macro]
        return tags
    
    # ---------------------------------------------------------
    # PREVIDENCIÁRIO: detecção por ontologia → tags → hints
    # ---------------------------------------------------------
    def _prev_detect_paths(self, user_text: str, max_hits: int = 10) -> list[str]:
        t = _norm_txt(user_text)
        hits: list[str] = []
        for path, label in _iter_ontology_paths(_PREVID_ONTOLOGY):
            if label and label in t and path not in hits:
                hits.append(path)
                if len(hits) >= max_hits:
                    break
        return hits

    def _prev_tags_from_paths(self, paths: list[str]) -> list[str]:
        tags: list[str] = []
        for p in paths:
            leaf = p.split(".")[-1]
            tags.append(f"prev_{leaf}")
        # dedup + limite
        seen, out = set(), []
        for tg in tags:
            if tg not in seen:
                seen.add(tg)
                out.append(tg)
        return out[:16]

    def _prev_hints(self, paths_or_tags: list[str], max_hints: int = 10) -> list[str]:
        hints: list[str] = []
        for key in paths_or_tags[:8]:
            node = None
            if key.startswith("prev_"):
                leaf = key[len("prev_"):]
                for p, _ in _iter_ontology_paths(_PREVID_ONTOLOGY):
                    if p.endswith("." + leaf) or p == leaf:
                        node = _get_node_by_path(_PREVID_ONTOLOGY, p)
                        break
            else:
                node = _get_node_by_path(_PREVID_ONTOLOGY, key)

            if node is None:
                continue
            items = node if isinstance(node, list) else (list(node.keys()) if isinstance(node, dict) else [str(node)])
            for it in items:
                h = _norm_txt(str(it))
                if h and h not in hints:
                    hints.append(h)
                if len(hints) >= max_hints:
                    return hints
        return hints

    def _maybe_add_prev_macro(self, tags: list[str], prev_paths: list[str]) -> list[str]:
        macro = "direito_previdenciario"
        if prev_paths and macro not in tags:
            tags = tags + [macro]
        return tags
    
     # ---------------------------------------------------------
    # AMBIENTAL: detecção por ontologia → tags → hints
    # ---------------------------------------------------------
    def _amb_detect_paths(self, user_text: str, max_hits: int = 10) -> list[str]:
        t = _norm_txt(user_text)
        hits: list[str] = []
        for path, label in _iter_ontology_paths(_AMBIENTAL_ONTOLOGY):
            if label and label in t and path not in hits:
                hits.append(path)
                if len(hits) >= max_hits:
                    break
        return hits

    def _amb_tags_from_paths(self, paths: list[str]) -> list[str]:
        tags: list[str] = []
        for p in paths:
            leaf = p.split(".")[-1]
            tags.append(f"amb_{leaf}")
        # dedup + limite
        seen, out = set(), []
        for tg in tags:
            if tg not in seen:
                seen.add(tg)
                out.append(tg)
        return out[:16]

    def _amb_hints(self, paths_or_tags: list[str], max_hints: int = 10) -> list[str]:
        hints: list[str] = []
        for key in paths_or_tags[:8]:
            node = None
            if key.startswith("amb_"):
                leaf = key[len("amb_"):]
                for p, _ in _iter_ontology_paths(_AMBIENTAL_ONTOLOGY):
                    if p.endswith("." + leaf) or p == leaf:
                        node = _get_node_by_path(_AMBIENTAL_ONTOLOGY, p)
                        break
            else:
                node = _get_node_by_path(_AMBIENTAL_ONTOLOGY, key)

            if node is None:
                continue
            items = (
                node
                if isinstance(node, list)
                else (list(node.keys()) if isinstance(node, dict) else [str(node)])
            )
            for it in items:
                h = _norm_txt(str(it))
                if h and h not in hints:
                    hints.append(h)
                if len(hints) >= max_hints:
                    return hints
        return hints

    def _maybe_add_amb_macro(self, tags: list[str], amb_paths: list[str]) -> list[str]:
        macro = "direito_ambiental"
        if amb_paths and macro not in tags:
            tags = tags + [macro]
        return tags

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
        # boosts semânticos ajudam a recuperar trechos jurídicos mais precisos
        q.extend(self._legal_query_boost(user_text))
        return [s for s in q if s and len(s) > 3]
    
    def _expand_with_legal_synonyms(self, queries: list[str], tags: list[str]) -> list[str]:
        syn = {
            # --- Civil/Consumidor/Imobiliário (exemplos do patch anterior) ---
            "honra_online": ["difamação internet", "remoção de conteúdo", "tutela de urgência", "direito de imagem"],
            "responsabilidade_civil": ["dano moral", "ato ilícito", "reparação civil"],
            "veiculo_nao_transferido": ["transferência de propriedade veículo", "obrigação de fazer Detran", "comunicado de venda"],
            "vizinhança": ["direito de vizinhança", "obras NBR", "interdito proibitório liminar"],
            "contratos": ["inadimplemento contratual", "cláusula penal", "rescisão perdas e danos"],
            "consumidor": ["CDC", "prática abusiva", "responsabilidade objetiva"],
            "imobiliario": ["escritura registro", "adjudicação compulsória", "averbação matrícula"],

            # --- CPC (atalhos úteis) ---
            "cpc_tutela_de_urgencia": ["probabilidade do direito", "periculum in mora", "reversibilidade", "contracautela"],
            "cpc_tutela_de_evidencia": ["hipóteses legais", "abuso do direito de defesa", "prova documental robusta"],
            "cpc_agravo_de_instrumento": ["taxatividade mitigada", "efeito suspensivo", "art 1.015 CPC"],
            "cpc_embargos_de_declaracao": ["omissão contradição obscuridade", "efeitos infringentes", "prazo interrupção"],
            "cpc_producao_antecipada_de_prova": ["urgência justo receio", "prova autônoma"],
            "cpc_execucao_de_titulo_extrajudicial": ["penhora avaliação expropriação", "exceção de pré-executividade", "embargos à execução"],

            # --- PENAL (principais folhas, focadas em consulta/base jurisprudencial) ---
            "direito_penal": ["Código Penal", "ação penal pública/privada", "tipicidade e ilicitude"],
            "penal_calunia": ["calúnia art 138", "falsa imputação de crime", "queixa-crime", "exceção da verdade"],
            "penal_difamacao": ["difamação art 139", "ofensa à reputação", "composição civil", "queixa-crime"],
            "penal_injuria": ["injúria art 140", "ofensa à dignidade", "composição civil", "ação penal privada"],
            "penal_injuria_racial_lei_14532_2023": ["injúria racial Lei 14.532/2023", "ação penal pública incondicionada", "racismo/injúria racial"],
            "penal_ameaca": ["ameaça art 147", "medidas protetivas", "ação penal pública condicionada"],
            "penal_estelionato": ["estelionato art 171", "representação da vítima", "dolo antecedente"],
            "penal_furto_simples": ["furto art 155", "crime sem violência", "princípio da insignificância"],
            "penal_roubo_simples": ["roubo art 157", "grave ameaça", "arma de fogo majorante"],
            "penal_lesao_corporal_leve": ["lesão corporal art 129", "exame de corpo de delito", "ação penal (MP)"] ,
            "penal_lesao_domestica_violencia_maria_da_penha": ["Lei Maria da Penha", "medidas protetivas", "Juizado de Violência Doméstica"],
            "penal_homicidio_simples": ["homicídio art 121", "competência do júri", "pronúncia e impronúncia"],
            "penal_trafico_de_drogas": ["art 33 Lei 11.343", "tráfico privilegiado §4º", "dosimetria de pena"],
            "penal_embriaguez_ao_volante": ["art 306 CTB", "prova etilômetro e testemunhal", "crime de perigo abstrato"],

            # --- DPP (Direito Processual Penal) ---
            "direito_processual_penal": ["CPP", "prisões cautelares", "nulidades processuais"],
            "dpp_prisao_em_flagrante": ["auto de prisão", "audiência de custódia", "conversão em preventiva"],
            "dpp_prisao_preventiva": ["fumus commissi delicti", "periculum libertatis", "garantia da ordem pública"],
            "dpp_prisao_temporaria": ["lei 7.960/89", "prazo e prorrogação", "rol de crimes"],
            "dpp_medidas_cautelares_diversas": ["monitoramento eletrônico", "proibição de contato", "comparecimento periódico"],
            "dpp_audiencia_de_custodia": ["controle de legalidade", "maus tratos", "medidas alternativas"],
            "dpp_cadeia_de_custodia": ["coleta e preservação", "quebra de cadeia", "prova ilícita"],
            "dpp_interceptacao": ["lei 9.296/96", "fundamentação", "prazo e prorrogação"],
            "dpp_busca_e_apreensao": ["fundadas razões", "mandado", "horário e limites"],
            "dpp_denuncia_e_queixa": ["requisitos CPP 41", "aditamento", "recebimento e rejeição"],
            "dpp_acao_penal": ["pública condicionada", "representação da vítima", "privada subsidiária"],
            "dpp_recurso_em_sentido_estrito": ["hipóteses CPP 581", "prazo", "juízo de retratação"],
            "dpp_apelacao": ["efeito devolutivo", "sustentação oral", "sentença absolutória/condenatória"],
            "dpp_embargos": ["de declaração", "infringentes", "efeitos"],
            "dpp_habeas_corpus": ["constrangimento ilegal", "liberdade de locomoção", "liminar"],
            "dpp_revisao_criminal": ["erro de fato", "prova nova", "trânsito em julgado"],
            "dpp_juiz_das_garantias": ["controle da investigação", "separação de funções", "decisões sobre prisões"],
            "dpp_tribunal_do_juri": ["pronúncia", "impronúncia", "quesitação e plenário"],
            "dpp_acordo_de_nao_persecucao_penal": ["art 28-A CPP", "condições", "homologação"],
            "dpp_transacao_penal": ["Lei 9.099/95", "requisitos", "JECrim"],
            "dpp_suspensao_condicional_do_processo": ["art 89 Lei 9.099/95", "condições", "prazo"],
            "dpp_provas_ilicitas": ["frutos da árvore envenenada", "derivadas lícitas", "nulidade"],

            # --- EMPRESARIAL (NOVOS) ---
            "direito_empresarial": ["sociedade limitada", "sociedade anônima", "recuperação judicial"],

            "emp_sociedade_limitada": ["contrato social", "quotas", "administração"],
            "emp_sociedade_anonima": ["assembleia geral", "conselho de administração", "debêntures", "Lei 6.404/76"],
            "emp_transformacao_fusao_cisao_incorporacao": ["fusão", "cisão", "incorporação", "protocolo e justificação"],
            "emp_dissolucao_e_liquidacao": ["dissolução e liquidação", "liquidante", "prestação de contas"],
            "emp_cooperativas": ["princípios cooperativos", "responsabilidade dos cooperados"],

            "emp_titulos_de_credito": ["duplicata", "nota promissória", "cheque", "letra de câmbio", "protesto"],
            "emp_endosso": ["endosso translativo", "endosso-mandato", "endosso-caução"],
            "emp_aval": ["aval", "responsabilidade solidária", "execução por título"],
            "emp_protesto": ["protesto de títulos", "cancelamento de protesto"],

            "emp_contratos_empresariais": ["franquia", "representação comercial", "distribuição", "factoring", "leasing"],
            "emp_franquia": ["Lei 13.966/2019", "Circular de Oferta de Franquia (COF)"],
            "emp_representacao_comercial": ["Lei 4.886/65", "indenização por rescisão", "comissão"],
            "emp_factoring": ["cessão de crédito", "assunção de risco"],
            "emp_leasing": ["arrendamento mercantil", "financeiro", "operacional"],
            "emp_joint_ventures_e_parcerias": ["joint venture", "acordo de acionistas", "cláusula de não concorrência"],

            "emp_propriedade_industrial": ["INPI", "Lei 9.279/96", "licenciamento", "nulidade"],
            "emp_marcas": ["registro de marca", "colisão com nome empresarial"],
            "emp_patentes": ["patente de invenção", "modelo de utilidade", "licença"],
            "emp_concorrencia_desleal": ["parasitismo", "segredo industrial", "confusão"],

            "emp_crise_da_empresa": ["Lei 11.101/2005", "Lei 14.112/2020", "recuperação judicial", "falência"],
            "emp_recuperacao_judicial": ["plano de recuperação", "assembleia de credores", "classes de credores", "cram down"],
            "emp_falencia": ["quadro geral de credores", "arrecadação", "realização do ativo", "extinção das obrigações"],
            "emp_responsabilidade_dos_administradores": ["desconsideração da personalidade", "atos fraudulentos"],

            "emp_governanca_corporativa": ["compliance", "auditoria", "transparência"],
            "emp_direito_concorrencial": ["CADE", "ato de concentração", "cartel", "abuso de poder econômico"],
            "emp_sociedade_digital": ["LGPD", "proteção de dados", "blockchain", "smart contracts"],
            "emp_nome_empresarial": ["firma", "denominação", "colisão com marca"],
            "emp_estabelecimento": ["trespasse", "fundo de comércio", "aviamento"],

            # --- PREVIDENCIÁRIO (NOVOS) ---
            "direito_previdenciario": ["INSS", "RGPS", "benefício previdenciário"],

            # Seguridade / organização / custeio
            "prev_seguridade_social": ["saúde previdência assistência", "solidariedade social"],
            "prev_organizacao": ["RGPS", "RPPS", "regime complementar"],
            "prev_custeio": ["contribuição previdenciária", "CTC certidão de tempo de contribuição", "GPS/SEFIP"],

            # Segurados e qualidade
            "prev_obrigatorios": ["empregado", "contribuinte individual", "avulso", "segurado especial"],
            "prev_facultativos": ["facultativo", "estudante", "dona de casa"],
            "prev_qualidade_de_segurado": ["período de graça", "perda e recuperação da qualidade", "manutenção do vínculo"],
            "prev_dependentes": ["pensão por morte dependente", "classe I II III"],

            # Carência e tempo
            "prev_carencia": ["isenção de carência", "acidente de qualquer natureza"],
            "prev_tempo_de_contribuicao": ["CNIS", "CTPS", "tempo rural", "contagem recíproca"],
            "prev_tempo_especial_ppp_lcat_epi": ["PPP", "LCAT", "EPI", "agentes nocivos"],

            # Benefícios RGPS
            "prev_aposentadoria_por_idade": ["idade mínima", "carência", "regra de transição"],
            "prev_aposentadoria_por_tempo_de_contribuicao": ["pedágio", "fator previdenciário", "regra 85/95 progressiva"],
            "prev_aposentadoria_especial": ["PPP e LCAT", "agentes nocivos", "atividade especial"],
            "prev_aposentadoria_por_invalidez": ["incapacidade total e permanente", "conversão do auxílio-doença"],

            "prev_pensao_por_morte": ["qualidade de dependente", "duração por idade do dependente", "acumulação"],

            "prev_auxilios": ["auxílio-doença", "auxílio-acidente", "auxílio-reclusão"],
            "prev_auxilio_doenca_incapacidade_temporaria": ["benefício por incapacidade temporária", "perícia médica"],
            "prev_auxilio_acidente_reducao_da_capacidade": ["indenizatório", "redução da capacidade"],
            "prev_auxilio_reclusao": ["baixa renda", "qualidade de segurado"],

            "prev_salario_maternidade": ["carência por categoria", "segurada especial"],
            "prev_salario_familia": ["renda-limite", "comprovação de dependentes"],

            # RPPS
            "prev_beneficios_do_rpps": ["RPPS aposentadoria", "pensão RPPS", "regras de transição"],

            # Acumulação
            "prev_acumulacao_de_beneficios": ["vedações de acumular benefícios", "acumulação permitida RGPS/RPPS"],

            # Revisões
            "prev_revisao_da_vida_toda": ["salários anteriores a 1994", "temas repetitivos"],
            "prev_revisao_do_teto": ["EC 20/98 e EC 41/03", "limites de teto"],
            "prev_revisao_de_beneficio": ["erro de cálculo", "índice de correção", "fato novo"],
            "prev_desaposentacao": ["STF", "impossibilidade", "reaposentação"],

            # Processo previdenciário
            "prev_fase_administrativa": ["requerimento no INSS", "perícia médica", "recurso administrativo"],
            "prev_fase_judicial": ["Justiça Federal", "JEF", "tutela de urgência", "perícia judicial"],

             # --- AMBIENTAL (NOVOS) ---
            "direito_ambiental": ["meio ambiente", "licenciamento ambiental", "responsabilidade por dano ambiental"],

            # Fundamentos constitucionais
            "amb_principios": [
                "poluidor-pagador", "precaução", "prevenção", "desenvolvimento sustentável",
                "equidade intergeracional", "participação social"
            ],
            "amb_competencias_legislativas": [
                "competência concorrente", "competência municipal", "competência da União"
            ],

            # PNMA / SISNAMA / CONAMA
            "amb_lei_6938_1981": ["PNMA", "SISNAMA", "CONAMA", "instrumentos da PNMA"],
            "amb_instrumentos": ["licenciamento", "EIA/RIMA", "ZEE zoneamento", "auditoria ambiental", "relatórios de qualidade"],

            # Licenciamento e AIA
            "amb_licenciamento_ambiental": ["LP LI LO", "competência IBAMA/estados/municípios", "regularização"],
            "amb_eia_rima": ["conteúdo mínimo do EIA", "audiência pública", "controle judicial do EIA/RIMA"],
            "amb_dispensas_e_autorizacoes": ["licenciamento simplificado", "baixo impacto"],

            # Unidades de conservação / Código Florestal
            "amb_lei_9985_2000": ["SNUC", "proteção integral", "uso sustentável"],
            "amb_codigo_florestal_lei_12651_2012": ["APP", "Reserva Legal", "CRA", "CAR", "PRA"],
            "amb_patrimonio_cultural_paisagistico": ["tombamento", "área de proteção do patrimônio"],

            # Responsabilidade por dano ambiental
            "amb_responsabilidade_civil": ["objetiva", "risco integral", "dano moral coletivo", "solidariedade do poluidor"],
            "amb_responsabilidade_administrativa": ["auto de infração", "multas diárias", "embargo", "apreensão"],
            "amb_responsabilidade_penal": ["Lei 9605/1998", "crimes de poluição", "fauna e flora", "pessoa jurídica"],

            # Poluição e resíduos
            "amb_poluicao": ["poluição do ar/água/solo", "poluição sonora/visual/luminosa"],
            "amb_residuos_solidos": ["PNRS", "responsabilidade compartilhada", "logística reversa", "PGRS"],

            # Fauna e flora
            "amb_fauna": ["fauna silvestre", "pesca predatória", "tráfico de animais"],
            "amb_flora": ["desmatamento", "supressão de vegetação", "incêndios florestais", "exploração ilegal"],

            # Tutela coletiva ambiental
            "amb_acao_civil_publica": ["Lei 7347/85", "reparação e compensação", "dano moral coletivo"],
            "amb_acao_popular_ambiental": ["direito líquido e certo", "patrimônio público"],
            "amb_tac_termo_de_ajustamento_de_conduta": ["TAC", "execução de TAC"],
            "amb_mandado_de_segurança_ambiental": ["ato omissivo", "direito líquido e certo"],

            # Temas modernos
            "amb_mudancas_climaticas": ["PNMC", "redução de emissões", "créditos de carbono", "Acordo de Paris"],
            "amb_direito_ambiental_internacional": ["tratados", "conferências", "responsabilidades comuns porém diferenciadas"],
            "amb_economia_verde_e_sustentabilidade": ["energias renováveis", "PSA", "finanças sustentáveis"],
        }

        extras: list[str] = []
        for tg in tags:
            if tg in syn:
                extras.extend(syn[tg][:3])
            elif tg.startswith(("trib_", "cpc_", "penal_", "dpp_", "emp_", "prev_", "amb_"))
                extras.append(tg.replace("_", " "))

        seen, out = set(), []
        for q in queries + extras:
            qn = q.strip()
            if qn and qn not in seen:
                seen.add(qn)
                out.append(qn)
        return out[:12]

    def _query_rewrite(self, text: str) -> List[str]:
        p = (
            "Gere 3 a 5 consultas curtas (máx 6 palavras) sobre o caso, uma por linha, "
             "sem pontuação."
        )
        try:
            out = self._gen(
                [{"role": "user", "content": f"{p}\n\nCaso: {text}"}], max_new=80
            ) or ""
        except Exception:
            out = ""
        return [
            q.strip("•- ").lower()
            for q in out.splitlines()
            if q.strip()
        ][:5]
    
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
    
    def _relevance_score(self, query: str, chunk_text: str) -> float:
        import re
        stop = {
            "de","da","do","das","dos","a","o","e","é","em","um","uma","para","por","com","no","na",
            "ao","à","às","os","as","que","se","di","la","lo"
        }
        q = [w for w in re.findall(r"\w+", (query or "").lower()) if w not in stop]
        c = [w for w in re.findall(r"\w+", (chunk_text or "").lower()) if w not in stop]
        if not q or not c:
            return 0.0
        overlap = len(set(q) & set(c))
        return overlap / float(1 + min(len(set(q)), len(set(c))))

    def _filter_by_relevance(self, query: str, chunks: list, min_keep: int = 3, thr: float = 0.12):
        scored = []
        for c in chunks:
            txt = getattr(c, "text", "") or ""
            s = self._relevance_score(query, txt)
            scored.append((s, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        kept = [c for s, c in scored if s >= thr]
        if len(kept) < min_keep:
            kept = [c for _, c in scored[:max(min_keep, 1)]]
        return kept

    def _anti_generic(self, answer: str, user_text: str, src_pack: str) -> str:
        import re
        if not answer:
            return answer
        txt = (answer or "").lower()
        if re.search(r"\btema\s+(geral|c[ií]vel|civil)\b|quest[aã]o\s+(de\s+)?car[aá]ter\s+geral", txt):
            reprompt = (
                "A resposta ficou genérica. Reescreva específica ao caso, "
                "usando e citando obrigatoriamente os S# do SOURCE PACK e dando passos concretos "
                "(mínimo 4 passos no item 'O que fazer agora'). É proibido usar 'tema geral/ civil'.\n\n"
                f"PERGUNTA: {user_text}\n\nSOURCE PACK:\n{src_pack}"
            )
            ans2 = self._gen(
                [{"role": "system", "content": self.conf.system_prompt}, {"role": "user", "content": reprompt}],
                max_new=900,
            )
            if ans2:
                return ans2
        return answer

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
    
    def _enforce_specificity(self, answer: str, queries: list[str], tags: list[str]) -> str:
        if not answer:
            return answer
        txt_lower = (answer or "").lower()
        if "diagnóstico" in txt_lower or "diagnostico" in txt_lower or "[s" in txt_lower:
            return answer
        kws = [q for q in queries if q]
        cpc_hints = (
            self._cpc_hints([t for t in tags if t.startswith("cpc_")], max_hints=6)
            if any(t.startswith("cpc_") for t in tags)
            else []
        )
        penal_hints = (
            self._penal_hints([t for t in tags if t.startswith("penal_")], max_hints=6)
            if any(t.startswith("penal_") for t in tags)
            else []
        )
        dpp_hints = (
            self._dpp_hints([t for t in tags if t.startswith("dpp_")], max_hints=6)
            if any(t.startswith("dpp_") for t in tags)
            else []
        )
        trib_hints = (
            self._trib_hints([t for t in tags if t.startswith("trib_")], max_hints=6)
            if any(t.startswith("trib_") for t in tags)
            else []
        )
        emp_hints = (
            self._emp_hints([t for t in tags if t.startswith("emp_")], max_hints=6)
            if any(t.startswith("emp_") for t in tags)
            else []
        )
        prev_hints = (
            self._prev_hints([t for t in tags if t.startswith("prev_")], max_hints=6)
            if any(t.startswith("prev_") for t in tags)
            else []
        )
        amb_hints = (
            self._amb_hints([t for t in tags if t.startswith("amb_")], max_hints=6)
            if any(t.startswith("amb_") for t in tags)
            else []
        )
        hints = "; ".join(
            (kws[:8] + cpc_hints + penal_hints + dpp_hints + trib_hints + emp_hints + prev_hints + amb_hints)
        ) or "faça passos concretos, vinculados aos S#"
        prompt = (
            "A resposta a seguir ficou genérica. Reescreva de forma mais específica e prática, "
            "obrigatoriamente orientada à ação, considerando estes tópicos: "
            f"{hints}.\n\nRESPOSTA: {answer}"
        )
        try:
            improved = self._gen([{ "role": "user", "content": prompt }], max_new=400)
            return improved or answer
        except Exception:
            return answer


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
    

     # --- NOVO: boosts semânticos para consulta jurídica
    def _legal_query_boost(self, user_text: str) -> List[str]:
        t = (user_text or "").lower()
        seeds = [user_text]
        if any(k in t for k in ["bateram", "colisão", "acidente", "batida", "trânsito", "transito"]):
            seeds += [
                "responsabilidade civil",
                "acidente de trânsito",
                "danos materiais",
                "dever de indenizar",
            ]
        if any(k in t for k in ["caloteiro", "difama", "injúria", "injuria", "calúnia", "calunia", "honra"]):
            seeds += [
                "dano moral",
                "direito de personalidade",
                "honra objetiva",
                "responsabilidade civil extracontratual",
            ]
        if any(k in t for k in ["serasa", "spc", "negativa", "negativação", "negativacao"]):
            seeds += [
                "inscrição indevida",
                "cadastro de inadimplentes",
                "prova do débito",
                "CDC jurisprudência",
            ]
        return list(dict.fromkeys(seeds))

    # --- NOVO: detector simples de "hit" jurídico (jurisprudência/ementa)
    def _looks_like_juris(self, text: str) -> bool:
        t = (text or "").lower()
        keys = [
            "ementa",
            "tese",
            "precedente",
            "jurisprud",
            "relator",
            "acórdão",
            "acordao",
            "repetitivo",
        ]
        return any(k in t for k in keys)

    def _bnp_chunks(self, user_text: str, frame: dict, limit: int = 6) -> list:
        try:
            raw = self.bnp.search_precedents(user_text, frame, limit=limit) if getattr(self, "bnp", None) else []
            # normaliza em objetos similares a _Chunk
            out = []
            for r in raw:
                out.append(_Chunk(r.get("text",""), source=r.get("source","bnp_web"), metadata=r.get("metadata") or {}))
            return out
        except Exception:
            return []
    
    # --- NOVO: web search com lista branca de domínios oficiais
    def _web_search_law(self, user_text: str, k: int = 6) -> List[_Chunk]:
        if not (self.conf.use_web and getattr(self, "tavily", None)):
            return []
        qparts = self._legal_query_boost(user_text)
        include_domains_priority = [
            ["pangeabnp.pdpj.jus.br", "bnp.pdpj.jus.br", "pdpj.jus.br"],
            ["stj.jus.br", "stf.jus.br", "tst.jus.br"],
            ["trf1.jus.br", "trf2.jus.br", "trf3.jus.br", "trf4.jus.br", "trf5.jus.br"],
            [
                "tjmg.jus.br",
                "tjsp.jus.br",
                "tjrs.jus.br",
                "tjba.jus.br",
                "tjpr.jus.br",
                "tjce.jus.br",
            ],
        ]
        out: List[_Chunk] = []
        try:
            for doms in include_domains_priority:
                for base in qparts[:3]:
                    try:
                        res = self.tavily.search(
                            f"{base} {user_text}",
                            include_domains=doms,
                            search_depth="advanced",
                            max_results=4,
                        )
                    except Exception:
                        res = self.tavily.search(f"{base} {user_text}")
                    items = (res or {}).get("results", []) if isinstance(res, dict) else []
                    for it in items:
                        title = (it.get("title") or "").strip()
                        content = (it.get("content") or "").strip()
                        url = (it.get("url") or "").strip()
                        if not url:
                            continue
                        blob = f"{title}\n{content}\nFonte: {url}".strip()
                        if self._looks_like_juris(blob):
                            out.append(_Chunk(blob, source=url, metadata={"domain": doms}))
                        if len(out) >= k:
                            return out
                if out:
                    break
        except Exception:
            logging.exception("Falha na _web_search_law.")
        return out[:k]


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

        auto_tags: list[str] = []

        cpc_paths = self._cpc_detect_paths(user_text)
        cpc_tags = self._cpc_tags_from_paths(cpc_paths)

        penal_paths = self._penal_detect_paths(user_text)
        penal_tags = self._penal_tags_from_paths(penal_paths)

        # >>> DPP (NOVO)
        dpp_paths = self._dpp_detect_paths(user_text)
        dpp_tags = self._dpp_tags_from_paths(dpp_paths)

        # TRIBUTÁRIO (novo)
        trib_paths = self._trib_detect_paths(user_text)
        trib_tags  = self._trib_tags_from_paths(trib_paths)
        
        # EMPRESARIAL (novo)
        emp_paths = self._emp_detect_paths(user_text)
        emp_tags  = self._emp_tags_from_paths(emp_paths)

        # PREVIDENCIÁRIO (novo)
        prev_paths = self._prev_detect_paths(user_text)
        prev_tags  = self._prev_tags_from_paths(prev_paths)

         # AMBIENTAL (novo)
        amb_paths = self._amb_detect_paths(user_text)
        amb_tags  = self._amb_tags_from_paths(amb_paths)

        # Consolidação de tags (inclua emp_tags)
        tags = list({
            *(frame.get("tags") or []),
              *auto_tags, *cpc_tags, *penal_tags, *dpp_tags, *trib_tags, *emp_tags, *prev_tags,
             *amb_tags
        })

        # Macros por área
        tags = self._maybe_add_cpc_macro(tags, cpc_paths)
        tags = self._maybe_add_penal_macro(tags, penal_paths)
        tags = self._maybe_add_dpp_macro(tags, dpp_paths)
        tags = self._maybe_add_trib_macro(tags, trib_paths)
        tags = self._maybe_add_emp_macro(tags, emp_paths)
        tags = self._maybe_add_prev_macro(tags, prev_paths)
        tags = self._maybe_add_amb_macro(tags, amb_paths)
        frame["tags"] = tags

        queries = self._expand_queries(user_text, frame)
        # Expansão de consultas com sinônimos (inclui DPP agora)
        queries = self._expand_with_legal_synonyms(queries, tags)
        extra = expand_query(user_text, max_items=6)
        for q in extra:
            if q not in queries:
                queries.append(q)
        logging.info("queries=%s", queries[:4])
        chunks = self._retrieve_multi(queries, k=self.conf.retriever_k)
        if len(chunks) < self.conf.min_rag_chunks:
            rew = self._query_rewrite(user_text)
            if rew:
                chunks2 = self._retrieve_multi(
                     rew + queries[:2], k=self.conf.retriever_k
                )
                if len(chunks2) > len(chunks):
                    chunks = chunks2
        chunks = self._filter_by_relevance(user_text, chunks, min_keep=3, thr=0.12)
        coverage = self._score_pdf_coverage(chunks)
        logging.info(
             "RAG multi: q=%d chunks=%d coverage=%.2f", len(queries), len(chunks), coverage
        )
        needs_web_law = (coverage < self.conf.coverage_threshold) or not any(
            self._looks_like_juris(getattr(c, "text", "")) for c in chunks
        )
        if needs_web_law:
            bnp_hits = self._web_search_law(
                user_text, k=max(3, self.conf.retriever_k // 2)
            )
            if bnp_hits:
                chunks = bnp_hits + chunks
        web_ctx = ""
        if (
            coverage < self.conf.coverage_threshold
            and not self._is_low_signal_query(user_text)
            and not any(self._looks_like_juris(getattr(c, "text", "")) for c in chunks)
        ):
            tags = " ".join((frame.get("tags") or [])[:3])
            web_ctx = self._safe_web_search(f"{user_text} {tags}".strip())
            if web_ctx:
                chunks = chunks + [type("WebChunk", (object,), {"text": web_ctx})()]
        bnp_more = self._bnp_chunks(user_text, frame, limit=4)
        if bnp_more:
            have = {" ".join((getattr(c, "text","") or "")[:120].split()).lower() for c in chunks}
            for c in bnp_more:
                sig = " ".join((getattr(c, "text","") or "")[:120].split()).lower()
                if sig not in have:
                    chunks.append(c)
                    have.add(sig)

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
        answer = self._enforce_specificity(answer, queries, tags)
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
        answer = self._anti_generic(answer, user_text, src_pack)
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
    try:
        from .buscador_pdf import BuscadorPDF
        buscador = BuscadorPDF(
            openai_key=os.getenv("OPENAI_API_KEY", ""),
            tavily_key=os.getenv("TAVILY_API_KEY"),
            pdf_dir=os.getenv("PDFS_DIR", "data/pdfs"),
            index_dir=get_index_dir(),
        )
    except Exception as e:  # pragma: no cover - defensivo
        logging.exception("Falha ao inicializar BuscadorPDF: %s", e)
        class BuscadorStub:
            def retrieve(self, query: str, k: int = 4) -> List[Any]:
                return []

            def buscar_contexto(self, consulta: str, k: int = 5) -> str:
                return ""

        buscador = BuscadorStub()

    datajud_enabled = os.getenv("DATAJUD_ENABLE", "true").lower() in {"1", "true", "yes", "on"}
    datajud_retr = None
    if datajud_enabled:
        try:
            dj_client = DatajudClient(api_key=os.getenv("DATAJUD_API_KEY"))
            datajud_retr = DatajudRetriever(client=dj_client, size=int(os.getenv("DATAJUD_SIZE", "10")))
        except Exception:
            logging.exception("Datajud não inicializado.")

    web_enabled = os.getenv("WEB_ENABLE", "true").lower() in {"1", "true", "yes", "on"}
    web_retr = None

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
    
    if web_enabled and tavily:
        try:
            web_retr = WebRetriever(tavily_client=tavily, num_results=int(os.getenv("WEB_NUM_RESULTS", "8")))
        except Exception:
            logging.exception("WebRetriever/Tavily não inicializado.")

    retrievers = [buscador]
    if datajud_retr:
        retrievers.append(datajud_retr)
    if web_retr:
        retrievers.append(web_retr)
    combined = CombinedRetriever(retrievers, max_per_source=6, chunk_max_chars=450)
    retriever = combined
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

