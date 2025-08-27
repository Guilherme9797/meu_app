from __future__ import annotations
import os, math
from dataclasses import dataclass

@dataclass
class PricingInput:
    resumo: str
    valor_economico_brl: float | None = None

@dataclass
class PricingResult:
    sugerido_brl: float
    minimo_brl: float
    categoria: str = "modelo_pricing"

class PricingService:
    """
    Precificação simples e parametrizável por ambiente.
      - PRICING_MIN_BRL: piso mínimo (default 1200)
      - PRICING_RATE: % sobre o valor econômico (default 0.08 = 8%)
      - PRICING_ROUND_STEP: arredondamento para cima em múltiplos (default 5)
    """
    def __init__(self):
        self.minimo = float(os.getenv("PRICING_MIN_BRL", "1200"))
        self.rate = float(os.getenv("PRICING_RATE", "0.08"))
        self.round_step = int(os.getenv("PRICING_ROUND_STEP", "5"))

    def _round_up(self, x: float) -> float:
        step = max(1, self.round_step)
        return math.ceil(x / step) * step

    def sugerir(self, data: PricingInput) -> PricingResult:
        base = float(data.valor_economico_brl or 0.0)
        if base <= 0:
            s = self._round_up(self.minimo)
            return PricingResult(sugerido_brl=s, minimo_brl=self.minimo)
        bruto = base * self.rate
        s = self._round_up(max(self.minimo, bruto))
        return PricingResult(sugerido_brl=s, minimo_brl=self.minimo)
