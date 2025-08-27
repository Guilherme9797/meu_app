from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
import os, json, math

@dataclass
class PricingInput:
    resumo: str
    valor_economico_brl: Optional[float] = None

@dataclass
class PricingSuggest:
    sugerido_brl: float
    minimo_brl: float
    categoria: str

def _round_to(x: float, step: int) -> float:
    step = max(1, int(step))
    return math.ceil(float(x) / step) * step

class PricingService:
    """
    Regras simples com suporte a:
      - piso por categoria (via env PRICING_TABLE_JSON/PRICING_TABLE_PATH)
      - markup padrão (PRICING_MARKUP) e por categoria (PRICING_MARKUP_BY_CATEGORY)
      - arredondamento (PRICING_ROUND_TO)
      - fallback: mínimo = 20% do SM (ou R$300), sugerido = max(mínimo, 6% do valor econômico) * (1+markup)
    """
    def __init__(self) -> None:
        self.round_to = int(os.getenv("PRICING_ROUND_TO", "50"))
        self.markup = float(os.getenv("PRICING_MARKUP", "0.25"))
        try:
            self.markup_by_cat = json.loads(os.getenv("PRICING_MARKUP_BY_CATEGORY", "") or "{}")
        except Exception:
            self.markup_by_cat = {}
        self.sm = float(os.getenv("SALARIO_MINIMO_BRL", "1412"))
        self.table = self._load_table()

    def _load_table(self) -> Dict[str, float]:
        path = os.getenv("PRICING_TABLE_PATH") or ""
        js = os.getenv("PRICING_TABLE_JSON") or ""
        data: Dict[str, float] = {}
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        if not data and js:
            try:
                data = json.loads(js)
            except Exception:
                data = {}
        return {str(k).strip().lower(): float(v) for k, v in data.items() if v}

    def _categoria(self, resumo: str) -> str:
        r = (resumo or "").lower()
        if "alimentos" in r or "família" in r or "familia" in r:
            return "familia"
        if "consum" in r:
            return "consumidor"
        if "trabalh" in r:
            return "trabalhista"
        if "penal" in r or "crime" in r:
            return "penal"
        return "geral"

    def sugerir(self, data: PricingInput) -> PricingSuggest:
        cat = self._categoria(data.resumo)
        piso = float(self.table.get(cat, 0.0) or 0.0)
        if piso <= 0:
            piso = max(300.0, 0.2 * self.sm)  # fallback de piso
        base = float(data.valor_economico_brl or 0.0)
        # 6% do valor econômico como base, com markup
        mark = float(self.markup_by_cat.get(cat, self.markup))
        sug = base * 0.06 if base > 0 else piso
        sug = sug * (1.0 + mark)
        sug = max(piso, _round_to(sug, self.round_to))
        return PricingSuggest(sugerido_brl=float(sug), minimo_brl=float(piso), categoria=cat)
