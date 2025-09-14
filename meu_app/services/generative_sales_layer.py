from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import json
import re

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
    def __init__(self, llm_client, pricing: Optional[PricingPolicy] = None):
        self.llm = llm_client
        self.pricing = pricing or DEFAULT_PRICING

    def _build_system(self) -> str:
        return GEN_PROMPT + "Schema:" + json.dumps(GEN_SCHEMA, ensure_ascii=False)

    def _llm_plan(self, text: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": self._build_system()},
            {"role": "user", "content": text.strip()[:4000]},
        ]
        # Use your LLM wrapper (must return string)
        raw = self.llm.chat(messages=messages, temperature=0.3)
        # Extract JSON from response
        m = re.search(r"\{[\s\S]*\}$", raw.strip())
        j = json.loads(m.group(0)) if m else json.loads(raw)
        return j

    def compose_reply(self, session, user_text: str) -> str:
        plan = self._llm_plan(user_text)
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