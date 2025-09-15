from typing import Optional, List
from .pricing import Pricing, fmt_brl

_pricing = Pricing()

def build_offer_from_playbook(pricing_services: List[str], budget_tone: Optional[str], deadline: Optional[str]) -> str:
    urg = f"Seu prazo/audiência é **{deadline}**." if deadline else "Vamos agir de forma rápida e segura."
    resolved = _pricing.resolve_services(pricing_services[:3] or ["Consulta Estratégica","Acompanhamento Inicial"])
    lines = []
    for label, min_fee, _code in resolved:
        anc = _pricing.anchor_price(min_fee)
        cash = _pricing.best_cash_price(anc, min_fee)
        nego = _pricing.negotiate(anc, min_fee, budget_tone)
        # parcelamento simples por ticket
        parcels = "1x no Pix/Cartão" if anc <= 400 else ("entrada + 2x" if anc <= 1200 else "entrada + 3x")
        lines.append(f"• **{label}** — **{fmt_brl(anc)}** (à vista {fmt_brl(cash)} ou {parcels}; negociação até {fmt_brl(nego)})")

    blocks = [
        urg,
        "Plano de ação:",
        # quem define os passos é o próprio playbook (montado pelo LLM)
    ]
    return "\n".join(blocks) + "\n\n" + "\n".join(lines)
