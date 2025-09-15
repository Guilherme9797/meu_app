from dataclasses import dataclass
import logging
from typing import Dict, Optional

import requests


logger = logging.getLogger(__name__)


# Fallback estático — OAB-GO 2025 (cap. 28)
OAB_GO_2025: Dict[str, float] = {
    "TRÂNSITO_DEFESA_PREVIA": 419.08,  # 28.1.1
    "TRÂNSITO_JARI": 628.62,  # 28.1.2
    "TRÂNSITO_CETRAN": 942.93,  # 28.1.3
    "TRÂNSITO_PACOTE_3_ETAPAS": 1885.86,  # 28.1.4
    "TRÂNSITO_JUDICIAL_ANULATORIA": 4190.80,  # 28.2.1/28.2.2 (mín.)
}


@dataclass
class PricePolicy:
    # markup de ancoragem sobre o mínimo da OAB
    anchor_markup: float = 0.35   # 35% acima do piso para “dar desconto”
    # desconto padrão à vista (opcional)
    cash_discount: float = 0.10   # 10% à vista
    # teto de desconto em negociação (nunca abaixo do mínimo OAB)
    max_negotiation_discount: float = 0.20  # até 20% sobre o preço âncora


def fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class FeeProvider:
    def __init__(self, table: Dict[str, float]):
        self.table = table

    def get_min(self, code: str) -> float:
        return self.table[code]


class TalilyClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = base_url
        self.token = token

    def get_min(self, jurisdiction: str, code: str) -> Optional[float]:
        if not self.base_url:
            return None

        try:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            response = requests.get(
                self.base_url.rstrip("/"),
                params={"jurisdiction": jurisdiction, "code": code},
                headers=headers,
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("talily_min_fee_lookup_failed jurisdiction=%s code=%s error=%s", jurisdiction, code, exc)
            return None

        for key in ("min_fee", "minimum_fee", "value", "amount"):
            value = data.get(key)
            if isinstance(value, (int, float)):
                return float(value)

        logger.info("talily_min_fee_lookup_no_value jurisdiction=%s code=%s payload=%s", jurisdiction, code, data)
        return None


class Pricing:
    def __init__(self, talily: Optional[TalilyClient] = None, policy: Optional[PricePolicy] = None):
        self.talily = talily or TalilyClient()
        self.policy = policy or PricePolicy()
        self.fallback = FeeProvider(OAB_GO_2025)

    def min_fee(self, code: str, jurisdiction: str = "GO") -> float:
        v = self.talily.get_min(jurisdiction, code)
        return v if v else self.fallback.get_min(code)

    def anchor_price(self, min_fee: float) -> float:
        return round(min_fee * (1 + self.policy.anchor_markup), 2)

    def best_cash_price(self, anchored: float, min_fee: float) -> float:
        # preço à vista com desconto, respeitando piso OAB
        cash = round(anchored * (1 - self.policy.cash_discount), 2)
        return max(cash, min_fee)

    def negotiate(self, anchored: float, min_fee: float, tone: Optional[str]) -> float:
        # reduz markup se cliente sinaliza orçamento apertado
        max_disc = self.policy.max_negotiation_discount
        if tone == "apertado":
            max_disc = min(0.30, max_disc + 0.10)  # pode ir até 30% se apertado
        target = round(anchored * (1 - max_disc), 2)
        return max(target, min_fee)