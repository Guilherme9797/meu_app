from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import json
import re

# ----------------------------------------------------------------------------
# Pricing policy (optional, keeps messages generic if you do not set numbers)
# ----------------------------------------------------------------------------

@dataclass
class PricingPolicy:
    tiers: Dict[str, str]

DEFAULT_PRICING = PricingPolicy(tiers={
    "consulta": "acessível",
    "medida_extrajudicial": "em conta",
    "acao_judicial": "somente se necessário",
})

# ----------------------------------------------------------------------------
# Objection detection (heuristic) — complements LLM label
# ----------------------------------------------------------------------------

OBJ_MAP: Dict[str, List[str]] = {
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

# ----------------------------------------------------------------------------
# Anchoring helper
# ----------------------------------------------------------------------------

def price_anchor(policy: PricingPolicy) -> List[str]:
    tiers = policy.tiers or {}
    out: List[str] = []
    if tiers.get("consulta"):
        out.append(f"Consulta {tiers['consulta']}")
    if tiers.get("medida_extrajudicial"):
        out.append(f"Medida extrajudicial {tiers['medida_extrajudicial']}")
    if tiers.get("acao_judicial"):
        out.append(f"Ação judicial {tiers['acao_judicial']}")
    return out or ["Começamos pelo passo mais econômico e só escalamos se precisar."]

# ----------------------------------------------------------------------------
# Schema + prompt (V2): adds cost_benefit, urgency, questions_plan
# ----------------------------------------------------------------------------

GEN_SCHEMA_V2: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "domain": {"type": "string"},
        "empathy": {"type": "string"},
        "risk": {"type": "string"},
        "benefit": {"type": "string"},
        "example": {"type": "string", "description": "Use 'exemplo comum/ilustrativo' em 1 frase. Não alegue caso real específico."},
        "cost_benefit": {"type": "string", "description": "Linha de valor: investimento pequeno vs. prejuízo maior, adaptada ao domínio."},
        "urgency": {"type": "string", "description": "Urgência prática em 1 frase, sem alarmismo."},
        "objection_label": {"type": "string", "description": "preco | processo | sozinho | parcelar | tempo | risco | nenhum"},
        "questions_plan": {"type": "array", "items": {"type": "string"}, "description": "3–5 perguntas curtas priorizadas (1) docs básicos, (2) provas/valores, (3) registro/autoridades)."},
        "step_question": {"type": "string"},
        "cta_primary": {"type": "string"},
        "cta_alternatives": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "domain", "empathy", "risk", "benefit", "cost_benefit", "urgency",
        "objection_label", "step_question", "cta_primary", "questions_plan"
    ],
}

GEN_PROMPT_V2 = (
    "Você é um assistente jurídico em pt-BR para WhatsApp, com foco em conversão com ética.\n"
    "Objetivo: responder cliente leigo que pede 'só informação' e conduzir para próximo passo.\n"
    "Estilo: curto, humano, sem juridiquês; 1 pergunta por turno; linguagem clara e gentil.\n"
    "Sempre produzir JSON no schema fornecido.\n"
    "Conteúdo obrigatório:\n"
    "- Empatia breve;\n"
    "- Risco + benefício (o que perde se nada fizer, o que ganha se agir);\n"
    "- 'cost_benefit': linha de valor (ex.: 'é um investimento pequeno para evitar prejuízo maior'), adaptada ao caso;\n"
    "- 'urgency': 1 frase criando urgência prática (sem alarmismo);\n"
    "- 'example': exemplo comum/ilustrativo em 1 frase (não alegue caso real específico);\n"
    "- Detecte objeção (preço, fazer sozinho, medo de processo, tempo, parcelar, risco) e rotule em 'objection_label';\n"
    "- 'questions_plan': 3–5 perguntas curtas e priorizadas: 1) documentos básicos, 2) provas/valores, 3) registro/autoridades;\n"
    "- 'step_question': escolha a próxima pergunta do plano;\n"
    "- CTA primário e alternativas curtas.\n"
)

# ----------------------------------------------------------------------------
# QuestionPlanner: stepwise Qs with lightweight memory
# ----------------------------------------------------------------------------

class QuestionPlanner:
    KEY_PLAN = "q_plan"
    KEY_IDX = "q_idx"

    def __init__(self, session):
        self.session = session
        if not hasattr(self.session, "meta"):
            self.session.meta = {}

    def load_or_init(self, questions: List[str]) -> None:
        plan = self.session.meta.get(self.KEY_PLAN)
        if not plan:
            self.session.meta[self.KEY_PLAN] = (questions or [])[:5]
            self.session.meta[self.KEY_IDX] = 0

    def current(self) -> Optional[str]:
        plan = self.session.meta.get(self.KEY_PLAN) or []
        idx = int(self.session.meta.get(self.KEY_IDX, 0))
        return plan[idx] if 0 <= idx < len(plan) else None

    def advance(self) -> None:
        idx = int(self.session.meta.get(self.KEY_IDX, 0))
        self.session.meta[self.KEY_IDX] = idx + 1

    def answered_heuristic(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        # signal of concrete data
        return (
            any(k in t for k in [
                "sim", "tenho", "envio", "segue", "comprovante", "recibo", "contrato", "pix", "transfer", "cpf", "matrícula", "data", "valor", "laudo", "indeferimento", "bo", "processo"
            ])
            or bool(re.search(r"\d", t))
        )

# ----------------------------------------------------------------------------
# LLM Orchestrator V2
# ----------------------------------------------------------------------------

class GenerativeSalesLayer:
    def __init__(self, llm_client, pricing: Optional[PricingPolicy] = None):
        self.llm = llm_client
        self.pricing = pricing or DEFAULT_PRICING

    # keep your existing v1 methods if you want; V2 is additive

    def _build_system_v2(self) -> str:
        return GEN_PROMPT_V2 + "\nSchema:" + json.dumps(GEN_SCHEMA_V2, ensure_ascii=False)

    def _llm_plan_v2(self, text: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": self._build_system_v2()},
            {"role": "user", "content": (text or "").strip()[:4000]},
        ]
        raw = self.llm.chat(messages=messages, temperature=0.3)
        m = re.search(r"\{[\s\S]*\}$", raw.strip())
        j = json.loads(m.group(0)) if m else json.loads(raw)
        return j

    def compose_reply_v2(self, session, user_text: str) -> str:
        plan = self._llm_plan_v2(user_text)

        # 1) objection (llm + heuristics)
        llm_label = plan.get("objection_label", "nenhum")
        heur_label = detect_objection(user_text)
        label = heur_label if heur_label != "nenhum" else llm_label
        objection_line = {
            "preco": "Entendo o momento. Começamos pelo passo mais econômico (consulta e, se couber, medida extrajudicial) para evitar prejuízo maior.",
            "processo": "A ideia é evitar processo: primeiro tentamos resolver por via extrajudicial/acordo; judicial só se o outro lado não responder.",
            "sozinho": "Você pode tentar sozinho, mas uma peça técnica aumenta muito a chance de resolver rápido e evita resposta negativa. Posso fazer uma versão enxuta pra você.",
            "parcelar": "Podemos parcelar a etapa inicial, sim. Te mostro as opções ao final desta etapa.",
            "tempo": "Prazos variam, mas a etapa extrajudicial costuma ser rápida e já acelera o resto.",
            "risco": "Se nada for feito, o risco e o custo tendem a subir. A boa notícia é que dá pra começar simples e barato.",
            "nenhum": "",
        }[label]

        # 2) empathy + risk/benefit + cost-benefit + urgency + illustrative example
        blocks: List[str] = []
        if objection_line:
            blocks.append(objection_line)
        if plan.get("empathy"):
            blocks.append(plan["empathy"])
        rb = " ".join(x for x in [plan.get("risk"), plan.get("benefit")] if x)
        if rb:
            blocks.append(rb)
        cb = plan.get("cost_benefit") or "É um passo de baixo custo para evitar um prejuízo maior depois."
        ug = plan.get("urgency") or "Quanto antes iniciarmos, mais simples e barato tende a ser."
        blocks.append(cb)
        blocks.append(ug)
        ex = plan.get("example")
        if ex:
            blocks.append(ex)

        # 3) price anchor
        anchor_lines = price_anchor(self.pricing)
        blocks.append("Começamos enxuto e escalamos só se precisar:\n- " + "\n- ".join(anchor_lines))

        # 4) stepwise question planner
        planner = QuestionPlanner(session)
        planner.load_or_init(plan.get("questions_plan", []))
        if planner.answered_heuristic(user_text):
            planner.advance()
        q = planner.current() or plan.get("step_question") or "Qual é exatamente o problema e o resultado desejado?"
        blocks.append(q)

        # 5) CTA
        cta = plan.get("cta_primary")
        alts = plan.get("cta_alternatives", [])
        if cta:
            blocks.append(cta)
        if alts:
            blocks.extend(alts[:2])

        reply = "\n\n".join(b for b in blocks if b)
        if hasattr(session, "meta") and session.meta.get("channel") == "whatsapp":
            reply = reply.replace("\n\n", "\n")
            if len(reply) > 900:
                reply = reply[:850] + "... Quer que eu explique em áudio rápido?"
        return reply

# ----------------------------------------------------------------------------
# Wiring example (comment):
# ----------------------------------------------------------------------------
# from meu_app.utils.openai_client import LLM
# from meu_app.services.generative_sales_layer_v2 import GenerativeSalesLayer, DEFAULT_PRICING
#
# class AtendimentoService:
#     def __init__(self, ..., llm: Optional[LLM] = None):
#         self.llm = llm or LLM()
#         self.sales = GenerativeSalesLayer(self.llm, DEFAULT_PRICING)
#         ...
#     def handle_message(self, session, message: str) -> str:
#         user_text = message or ""
#         # ... your existing guard/classifier/tavily chain
#         return self.sales.compose_reply_v2(session, user_text)