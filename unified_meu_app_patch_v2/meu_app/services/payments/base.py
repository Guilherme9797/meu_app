from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class CheckoutResult:
    provider: str
    checkout_url: str
    provider_payment_id: str
    raw: Dict[str, Any]

class PaymentProvider:
    name: str = "base"
    def create_checkout(self, *, amount_centavos: int, currency: str, description: str,
                        success_url: str, cancel_url: str, customer: Dict[str, Any] | None,
                        proposta_id: str, payment_id: str) -> CheckoutResult:
        raise NotImplementedError
    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Retorna dict padronizado: {status:'paid'|'failed'|'unknown', provider_payment_id:str, paid_at:iso?} """
        raise NotImplementedError
