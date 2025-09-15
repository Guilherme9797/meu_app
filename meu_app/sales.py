from typing import Optional, Tuple

from .pricing import Pricing, fmt_brl


_pricing = Pricing()


def _plan_prices_trânsito(subtype: str, budget_tone: Optional[str]) -> Tuple[str, str, str]:
    min_defesa = _pricing.min_fee("TRÂNSITO_DEFESA_PREVIA")
    anc_defesa = _pricing.anchor_price(min_defesa)
    cash_defesa = _pricing.best_cash_price(anc_defesa, min_defesa)
    nego_defesa = _pricing.negotiate(anc_defesa, min_defesa, budget_tone)

    min_inter = min_defesa + _pricing.min_fee("TRÂNSITO_JARI")
    anc_inter = _pricing.anchor_price(min_inter)
    cash_inter = _pricing.best_cash_price(anc_inter, min_inter)
    nego_inter = _pricing.negotiate(anc_inter, min_inter, budget_tone)

    min_completo = _pricing.min_fee("TRÂNSITO_PACOTE_3_ETAPAS")
    anc_completo = _pricing.anchor_price(min_completo)
    cash_completo = _pricing.best_cash_price(anc_completo, min_completo)
    nego_completo = _pricing.negotiate(anc_completo, min_completo, budget_tone)


    planos = [
        (
            "Essencial",
            "Defesa prévia completa + protocolo + acompanhamento",
            anc_defesa,
            cash_defesa,
            nego_defesa,
            "entrada + 2x",
        ),
        (
            "Intermediário",
            "Defesa + Recurso na JARI (se necessário)",
            anc_inter,
            cash_inter,
            nego_inter,
            "entrada + 3x",
        ),
        (
            "Completo",
            "Defesa + JARI + CETRAN até decisão final",
            anc_completo,
            cash_completo,
            nego_completo,
            "entrada + 4x",
        ),
    ]
    lines = []
    for nome, desc, anc, cash, nego, parcel in planos:
        lines.append(
            f"• **{nome}** — {desc} — **{fmt_brl(anc)}** (à vista {fmt_brl(cash)} ou {parcel}; negociação até {fmt_brl(nego)})"
        )
    return "\n".join(lines), fmt_brl(min_defesa), fmt_brl(min_completo)


def build_offer_text(area: str, subtype: str, budget_tone: Optional[str], deadline: Optional[str]) -> str:
    urg = f"Seu prazo de defesa é **{deadline}**." if deadline else "Seu prazo de defesa está correndo."
    if area == "trânsito":
        lista, piso_defesa, piso_pacote = _plan_prices_trânsito(subtype, budget_tone)
        ancoragem = (
            "Trabalho orientado à tabela mínima da OAB-GO e com entrega completa em cada etapa. "
            "Eu adapto a forma de pagamento sem descumprir o piso da OAB."
        )
        return (
            f"{urg}\n\n"
            "Plano de ação:\n"
            "1) Montamos a defesa destacando ausência de oferta de exame alternativo e falhas formais;\n"
            "2) Protocolamos e acompanhamos; se necessário, seguimos para recurso(s).\n\n"
            f"{ancoragem}\n\n"
            f"Referência mínima OAB-GO: Defesa Prévia {piso_defesa} | Pacote 3 etapas {piso_pacote}.\n"
            f"Opções de honorários (ancoradas no mínimo OAB-GO):\n{lista}"
        )
    return urg