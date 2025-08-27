from __future__ import annotations
import uuid, datetime as dt
from typing import Dict, Any
from .base import PaymentProvider, CheckoutResult

class StripeProvider(PaymentProvider):
    name = "stripe"

    def create_checkout(self, *, amount_centavos: int, currency: str, description: str,
                        success_url: str, cancel_url: str, customer: Dict[str, Any] | None,
                        proposta_id: str, payment_id: str) -> CheckoutResult:
        pid = f"cs_test_{uuid.uuid4().hex[:24]}"
        url = f"https://checkout.stripe.test/{pid}"
        raw = {"simulated": True, "amount": amount_centavos, "currency": currency, "description": description}
        return CheckoutResult(provider=self.name, checkout_url=url, provider_payment_id=pid, raw=raw)

    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prov_id = None
        status = "unknown"
        paid_at = None
        if isinstance(payload, dict):
            t = (payload.get("type") or "").lower()
            obj = payload.get("data", {}).get("object", {})
            if t in {"checkout.session.completed", "payment_intent.succeeded"}:
                status = "paid"
            elif t in {"payment_intent.payment_failed"}:
                status = "failed"
            prov_id = obj.get("id") or payload.get("id")
            paid_at = obj.get("created")
        return {"status": status, "provider_payment_id": str(prov_id) if prov_id else None, "paid_at": paid_at}
