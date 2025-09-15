from typing import Optional, List
from .pricing import Pricing, fmt_brl

_pricing = Pricing()

def build_offer_from_playbook(
    pricing_services: List[str],
    plan_steps: Optional[List[str]],
    budget_tone: Optional[str],
    deadline: Optional[str],
) -> str:
    urg = f"Seu prazo/audiência é **{deadline}**." if deadline else "Vamos agir de forma rápida e segura."
    resolved = _pricing.resolve_services(pricing_services[:3] or ["Consulta Estratégica", "Acompanhamento Inicial"])
    lines: List[str] = []
    for label, min_fee, code in resolved:
        if code == "GENERIC_FALLBACK":
            lines.append(f"• **{label}** — valores sob consulta (alinhamos na primeira reunião).")
            continue
        anc = _pricing.anchor_price(min_fee)
        cash = _pricing.best_cash_price(anc, min_fee)
        nego = _pricing.negotiate(anc, min_fee, budget_tone)
        # parcelamento simples por ticket
        parcels = "1x no Pix/Cartão" if anc <= 400 else ("entrada + 2x" if anc <= 1200 else "entrada + 3x")
        lines.append(
            f"• **{label}** — **{fmt_brl(anc)}** (à vista {fmt_brl(cash)} ou {parcels}; negociação até {fmt_brl(nego)})"
        )

    blocks: List[str] = [urg]
    rendered_steps: List[str] = []
    for idx, step in enumerate(plan_steps or [], start=1):
        clean = (step or "").strip()
        if clean:
            rendered_steps.append(f"{idx}. {clean}")
    if rendered_steps:
        blocks.append("Plano de ação:")
        blocks.extend(rendered_steps)

    offer_header = "\n".join(blocks)
    pricing_block = "\n".join(lines)
    if offer_header and pricing_block:
        return offer_header + "\n\n" + pricing_block
    if offer_header:
        return offer_header
    return pricing_block
