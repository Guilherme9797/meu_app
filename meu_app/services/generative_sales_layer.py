from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import json
import re

# memória de caso
from .context_store import CaseRepository, InMemoryCaseRepository
from .case_state import CaseState

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
@dataclass
class PricingPolicy:
    """Optional ranges to anchor copy. If field missing, use generic wording.
    Keys are free-form (e.g., 'consulta', 'extrajudicial', 'judicial').
    Values are strings like 'R$150–R$350' or 'sob orçamento'.
    """
    tiers: Dict[str, str]

# valores mínimos segundo tabela de honorários da OAB/GO (2025)
# ajustar conforme atualização oficial
OAB_MIN_FEES: Dict[str, int] = {
    "consulta": 300,
    "medida_extrajudicial": 500,
    "acao_judicial": 1500,
}


DEFAULT_PRICING = PricingPolicy(tiers={
    "consulta": "R$300",
    "medida_extrajudicial": "R$500",
    "acao_judicial": "R$1500"
})

# ----------------------------------------------------------------------------
# Prompt + schema
# ----------------------------------------------------------------------------

GEN_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {"type": "string", "description": "Area of law in pt-BR, e.g., civil, penal, previdenciario, consumidor, trabalhista, empresarial, administrativo, constitucional, tributario."},
        "empathy": {"type": "string"},
        "risk": {"type": "string"},
        "benefit": {"type": "string"},
        "example": {"type": "string"},
        "objection_label": {"type": "string", "description": "one of: preco, processo, sozinho, parcelar, tempo, risco, nenhum"},
        "step_question": {"type": "string"},
        "cta_primary": {"type": "string"},
        "cta_alternatives": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["domain", "empathy", "risk", "benefit", "objection_label", "step_question", "cta_primary"]
}

GEN_PROMPT = (
    "Você é um assistente jurídico para WhatsApp respondendo como advogado brasileiro.\n"
    "Objetivo: converter um cliente leigo que pede 'só uma informação' em um próximo passo de contratação.\n"
    "Regras de estilo: curto, humano, sem juridiquês, focado em valor. 1 pergunta por turno.\n"
    "Sempre: empatia breve + risco/benefício + (se útil) exemplo/precedente simples + ancoragem de preço começando pelo menor custo + CTA.\n"
    "Se você detectar objeção (caro, posso fazer sozinho, medo de processo, demora, parcelar, risco), responda a objeção ANTES do restante.\n"
    "Saída em JSON no schema fornecido.\n"
)
# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------

OBJ_MAP = {
    "preco": ["caro", "gastar", "alto", "apertado", "sem dinheiro", "valor"],
    "processo": ["processo", "justiça", "juiz", "ação", "judicial"],
    "sozinho": ["fazer sozinho", "posso mandar", "sem advogado", "eu mesmo"],
    "parcelar": ["parcelar", "parcelamento", "parcelas"],
    "tempo": ["demora", "demorado", "quanto tempo"],
    "risco": ["perder", "risco", "problema maior"],
}
def detect_objection(text: str) -> str:
    t = (text or "").lower()
    for label, kws in OBJ_MAP.items():
        if any(k in t for k in kws):
            return label
    return "nenhum"


def _floor_price(desc: str, floor: int) -> str:
    """Enforces minimum price based on OAB table.
    If `desc` contains numbers, ensure the lowest value respects `floor`.
    """
    nums = [int(n) for n in re.findall(r"\d+", desc)]
    if not nums:
        return desc
    low = max(nums[0], floor)
    if len(nums) == 1:
        return f"R${low}"
    high = max(nums[1], low)
    return f"R${low}–R${high}"


def price_anchor(policy: PricingPolicy) -> List[str]:
    tiers = policy.tiers or {}
    out: List[str] = []
    if tiers.get("consulta"):
        desc = _floor_price(tiers["consulta"], OAB_MIN_FEES["consulta"])
        out.append(f"Consulta {desc}")
    if tiers.get("medida_extrajudicial"):
        desc = _floor_price(tiers["medida_extrajudicial"], OAB_MIN_FEES["medida_extrajudicial"])
        out.append(f"Medida extrajudicial {desc}")
    if tiers.get("acao_judicial"):
        desc = _floor_price(tiers["acao_judicial"], OAB_MIN_FEES["acao_judicial"])
        out.append(f"Ação judicial {desc}")
    return out or ["Começamos pelo passo mais econômico e só escalamos se precisar."]


# ----------------------------------------------------------------------------
# LLM Orchestrator
# ----------------------------------------------------------------------------

class GenerativeSalesLayer:
    def __init__(self, llm_client, pricing: Optional[PricingPolicy] = None, repo: Optional[CaseRepository] = None):
        self.llm = llm_client
        self.pricing = pricing or DEFAULT_PRICING
         # armazenamento persistente de estado do caso
        self.repo: CaseRepository = repo or InMemoryCaseRepository()

    def _build_system(self) -> str:
        return GEN_PROMPT + "Schema:" + json.dumps(GEN_SCHEMA, ensure_ascii=False)

    def _chat_id(self, session) -> str:
        raw = getattr(session, "phone", None) or getattr(session, "chat_id", "") or ""
        return re.sub(r"\D", "", raw)

    def _extract_and_merge(self, state: CaseState, text: str) -> None:
        t = (text or "").lower()
        docs = state.docs
        if any(k in t for k in ["relatorio", "atestado", "laudo"]):
            docs["relatorio"] = True
        if any(k in t for k in ["decisao", "decisão", "indeferimento", "negativa"]):
            docs["decisao"] = True
        if "cnis" in t:
            docs["cnis"] = True
        state.docs = docs

        if not state.benefit_type:
            if "bpc" in t:
                state.benefit_type = "bpc"
            elif "auxilio" in t or "auxílio" in t:
                state.benefit_type = "auxilio-doenca"
            elif "invalidez" in t:
                state.benefit_type = "aposentadoria por invalidez"

        date_matches = re.findall(r"\d{1,2}/\d{1,2}/\d{2,4}", text or "")
        for d in date_matches:
            if ("pericia" in t or "perícia" in t) and not state.pericia_date:
                state.pericia_date = d
            elif ("ciencia" in t or "ciência" in t) and not state.science_date:
                state.science_date = d
            elif ("indefer" in t or "negativa" in t) and not state.denial_date:
                state.denial_date = d

        if not state.cid:
            cid_match = re.search(r"\b[ABCD]\d{2}(?:\.\d{1,2})?\b", (text or "").upper())
            if cid_match:
                state.cid = cid_match.group(0)

    def _llm_plan_v2(self, text: str, facts: Dict[str, Any]) -> Dict[str, Any]:
        system = self._build_system()
        messages = [
            {"role": "system", "content": system},
            {
                "role": "system",
                "content": "USE OS FATOS ABAIXO. NÃO REPITA PERGUNTAS PARA SLOTS JÁ PREENCHIDOS.",
            },
            {"role": "system", "content": f"FATOS: {json.dumps(facts, ensure_ascii=False)}"},
            {"role": "user", "content": text.strip()[:4000]},
        ]
        # Use your LLM wrapper (must return string)
        raw = self.llm.chat(messages=messages, temperature=0.3)
        # Extract JSON from response
        m = re.search(r"\{[\s\S]*\}$", raw.strip())
        j = json.loads(m.group(0)) if m else json.loads(raw)
        return j

    def _missing_slots(self, state: CaseState) -> List[str]:
        wants = [
            ("benefit_type", state.benefit_type),
            ("science_date", state.science_date),
            ("denial_date", state.denial_date),
            ("pericia_date", state.pericia_date),
            ("cid", state.cid),
            ("docs.relatorio", state.docs.get("relatorio")),
            ("docs.decisao", state.docs.get("decisao")),
            ("docs.cnis", state.docs.get("cnis")),
        ]
        return [k for k, v in wants if not v and k not in state.asked_slots]

    def _question_for_slot(self, slot: str) -> Optional[str]:
        mapping = {
            "benefit_type": "Só confirmando: o benefício é auxílio-doença, aposentadoria por invalidez, BPC ou outro?",
            "science_date": "Qual a data de ciência da decisão no Meu INSS (aparece no PDF/print)?",
            "denial_date": "Qual a data do indeferimento no Meu INSS?",
            "pericia_date": "Qual a data da perícia médica?",
            "cid": "Seu relatório traz o CID? Se sim, qual é?",
            "docs.relatorio": "Você tem relatório/atestado médico atualizado para anexar?",
            "docs.decisao": "Você tem a decisão/indeferimento em PDF ou print do Meu INSS?",
            "docs.cnis": "Consegue emitir o CNIS no Meu INSS (menu Extratos) e me enviar?",
        }
        return mapping.get(slot)

    def _sanitize_questions(self, reply: str, state: CaseState) -> str:
        lines = [l.strip() for l in reply.split("\n") if l.strip()]

        def asks_about(line: str, slot: str) -> bool:
            probes = {
                "benefit_type": ["benefício é", "tipo de benefício", "auxílio-doença", "bpc", "invalidez"],
                "science_date": ["data de ciência"],
                "denial_date": ["data do indeferimento", "quando saiu a negativa"],
                "pericia_date": ["data da perícia"],
                "cid": ["cid"],
                "docs.relatorio": ["relatório", "atestado", "laudo"],
                "docs.decisao": ["decisão", "indeferimento", "print do meu inss"],
                "docs.cnis": ["cnis"],
            }
            return any(p in line.lower() for p in probes.get(slot, []))

        for slot, value in [
            ("benefit_type", state.benefit_type),
            ("science_date", state.science_date),
            ("denial_date", state.denial_date),
            ("pericia_date", state.pericia_date),
            ("cid", state.cid),
            ("docs.relatorio", state.docs.get("relatorio")),
            ("docs.decisao", state.docs.get("decisao")),
            ("docs.cnis", state.docs.get("cnis")),
        ]:
            if value:
                lines = [l for l in lines if not asks_about(l, slot)]

        missing = self._missing_slots(state)
        if missing:
            q = self._question_for_slot(missing[0])
            if q and all(q.lower() not in l.lower() for l in lines):
                lines.append(q)
                state.mark_asked(missing[0])

        return "\n".join(lines)

    def compose_reply(self, session, user_text: str) -> str:
        chat_id = self._chat_id(session)
        state = self.repo.get(chat_id) if chat_id else CaseState()

        self._extract_and_merge(state, user_text)
        facts = state.to_prompt_facts()
        plan = self._llm_plan_v2(user_text, facts)

        # merge domains/slots conhecidos
        allowed = set(state.__dict__.keys()) | {"docs"}
        merge_data = {k: v for k, v in plan.items() if k in allowed}
        if merge_data:
            state.merge(merge_data)
        # Objection (LLM label OR heuristic)
        llm_label = plan.get("objection_label", "nenhum")
        heur_label = detect_objection(user_text)
        label = heur_label if heur_label != "nenhum" else llm_label

        objection_line = {
            "preco": "Entendo o momento. A gente começa pelo passo mais econômico (consulta e, se couber, medida extrajudicial). É um investimento pequeno para evitar prejuízo maior.",
            "processo": "A ideia é evitar processo: primeiro tentamos resolver por medida extrajudicial/acordo. Só judicializamos se o outro lado não responder.",
            "sozinho": "Você até pode tentar sozinho, mas uma peça técnica aumenta muito a chance de solução e evita resposta negativa. Posso fazer uma versão enxuta pra você.",
            "parcelar": "Podemos parcelar a etapa inicial, sim. Te passo as opções ao final da triagem.",
            "tempo": "Prazo varia de caso a caso. A boa notícia é que a etapa extrajudicial costuma ser rápida e já acelera tudo.",
            "risco": "Sem agir, o risco e o custo tendem a subir. A boa notícia é que dá pra começar pelo passo mais simples e barato.",
            "nenhum": "",
        }[label]

        # Price anchor lines
        anchor_lines = price_anchor(self.pricing)

        # Assemble blocks
        blocks: List[str] = []
        if objection_line:
            blocks.append(objection_line)
        empathy = plan.get("empathy")
        rb = " ".join(x for x in [plan.get("risk"), plan.get("benefit")] if x)
        example = plan.get("example")
        if empathy:
            blocks.append(empathy)
        if rb:
            blocks.append(rb)
        if example:
            blocks.append(example)
        blocks.append("Começamos enxuto e escalamos só se precisar:\n- " + "\n- ".join(anchor_lines))

        # Step question + CTA
        q = plan.get("step_question") or "Qual é exatamente o problema e o resultado desejado?"
        blocks.append(q)
        state.mark_asked(q)
        cta = plan.get("cta_primary")
        alts = plan.get("cta_alternatives", [])
        if cta:
            blocks.append(cta)
        if alts:
            blocks.extend(alts[:2])

        reply = "\n\n".join(b for b in blocks if b)

        # Persist a simple step index if available
        if hasattr(session, "meta"):
            session.meta["q_step"] = int(session.meta.get("q_step", 0)) + 1
        if chat_id:
            self.repo.save(chat_id, state)
        return reply


# ----------------------------------------------------------------------------
# Wiring into AtendimentoService (example patch)
# ----------------------------------------------------------------------------

# from meu_app.utils.openai_client import LLM
# from meu_app.services.generative_sales_layer import GenerativeSalesLayer, DEFAULT_PRICING
#
# class AtendimentoService:
#     def __init__(self, ..., llm: Optional[LLM] = None):
#         self.llm = llm or LLM()
#         self.sales = GenerativeSalesLayer(self.llm, DEFAULT_PRICING)
#         ...
#
#     def handle_message(self, session, message: str) -> str:
#         user_text = message or ""
#         # ... (seu pipeline: classificador/guard/tavily, etc.)
#         reply = self.sales.compose_reply(session, user_text)
#         return reply