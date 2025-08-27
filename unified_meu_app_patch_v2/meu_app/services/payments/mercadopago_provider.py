from __future__ import annotations
import uuid, datetime as dt
from typing import Dict, Any
from .base import PaymentProvider, CheckoutResult

class MercadoPagoProvider(PaymentProvider):
    name = "mercadopago"

    def create_checkout(self, *, amount_centavos: int, currency: str, description: str,
                        success_url: str, cancel_url: str, customer: Dict[str, Any] | None,
                        proposta_id: str, payment_id: str) -> CheckoutResult:
        # Stub amigável para dev/teste sem acessar a API real
        pid = f"mp_{uuid.uuid4().hex[:18]}"
        url = f"https://checkout.mercadopago.test/{pid}"
        raw = {"simulated": True, "amount": amount_centavos, "currency": currency, "description": description}
        return CheckoutResult(provider=self.name, checkout_url=url, provider_payment_id=pid, raw=raw)

    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Normalização genérica
        prov_id = None
        status = "unknown"
        paid_at = None

        # tentativas razoáveis de extração
        if isinstance(payload, dict):
            prov_id = (payload.get("data") or {}).get("id") or payload.get("id") or payload.get("resourceId")
            st = (payload.get("status") or (payload.get("data") or {}).get("status") or "").lower()
            if st in {"approved", "paid", "succeeded"}:
                status = "paid"
            elif st in {"rejected", "failed", "canceled", "cancelled"}:
                status = "failed"
            # data de pagamento, se existir
            paid_at = (payload.get("date_approved")
                       or (payload.get("data") or {}).get("date_approved")
                       or (payload.get("payment") or {}).get("date_approved"))

        return {"status": status, "provider_payment_id": str(prov_id) if prov_id else None, "paid_at": paid_at}
