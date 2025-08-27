from __future__ import annotations
import os, uuid
from typing import Dict, Any, List
from .base import PaymentProvider, CheckoutResult
from .mercadopago_provider import MercadoPagoProvider
from .stripe_provider import StripeProvider

_ALL: Dict[str, PaymentProvider] = {
    "mercadopago": MercadoPagoProvider(),
    "stripe": StripeProvider(),
}

class PaymentOrchestrator:
    def __init__(self, provider_name: str | None = None) -> None:
        self.provider_name = (provider_name or os.getenv("PAYMENTS_PROVIDER", "mercadopago")).lower()
        if self.provider_name not in _ALL:
            self.provider_name = "mercadopago"
        self.provider = _ALL[self.provider_name]

    def create_checkout(self, **kwargs) -> CheckoutResult:
        return self.provider.create_checkout(**kwargs)

    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.provider.parse_webhook(payload)

    @staticmethod
    def available_providers() -> List[str]:
        return sorted(list(_ALL.keys()))
