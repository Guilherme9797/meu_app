from dataclasses import dataclass
from typing import List, Optional, Tuple
import logging

from .oab_catalog import search_codes_by_label, OABItem
from .tavily_client import fetch_minimum_for_label

logger = logging.getLogger(__name__)

@dataclass
class PricePolicy:
    anchor_markup: float = 0.35
    cash_discount: float = 0.10
    max_negotiation_discount: float = 0.20

def fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

class Pricing:
    def __init__(self, policy: Optional[PricePolicy] = None):
        self.policy = policy or PricePolicy()
    
    def resolve_services(self, labels: List[str]) -> List[Tuple[str, float, str]]:
        """
        Retorna [(service_label, min_fee, code)]
        Usa catálogo local; se não achar, tenta Tavily por label.
        """
        resolved = []
        for label in labels:
            items = search_codes_by_label(label, limit=1)
            if items:
                it: OABItem = items[0]
                min_fee = it.min_fee
                # opcional: tentar atualizar com Tavily (best effort)
                try:
                    v = fetch_minimum_for_label(it.name)
                    if isinstance(v, (int, float)) and v > 0:
                        min_fee = float(v)
                except Exception as exc:
                    logger.debug("pricing_tavily_lookup_failed label=%s error=%s", label, exc)
                resolved.append((label, min_fee, it.code))
            else:
                # label não encontrado → tenta Tavily direto
                v = None
                try:
                    v = fetch_minimum_for_label(label)
                except Exception as exc:
                    logger.debug("pricing_tavily_lookup_failed label=%s error=%s", label, exc)
                    v = None
                if isinstance(v, (int,float)) and v > 0:
                    resolved.append((label, float(v), "TAVILY_MATCH"))
                else:
                    # fallback seguro: consulta
                    logger.debug("pricing_catalog_fallback label=%s", label)
                    resolved.append((label, 300.00, "CONSULTA_FALLBACK"))
        return resolved

    def anchor_price(self, min_fee: float) -> float:
        return round(min_fee * (1 + self.policy.anchor_markup), 2)

    def best_cash_price(self, anchored: float, min_fee: float) -> float:
        cash = round(anchored * (1 - self.policy.cash_discount), 2)
        return max(cash, min_fee)

    def negotiate(self, anchored: float, min_fee: float, tone: Optional[str]) -> float:
        max_disc = self.policy.max_negotiation_discount
        if tone == "apertado":
             max_disc = min(0.30, max_disc + 0.10)
        target = round(anchored * (1 - max_disc), 2)
        return max(target, min_fee)