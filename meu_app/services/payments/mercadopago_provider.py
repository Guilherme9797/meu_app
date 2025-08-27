# meu_app/services/payments/mercadopago_provider.py
from __future__ import annotations
import os
import re
import requests
from typing import Dict, Any, Optional

from .base import PaymentProvider, CheckoutResult


class MercadoPagoProvider(PaymentProvider):
    """
    Provider de pagamentos (Mercado Pago) via Preferences (Checkout Pro).
    Requer:
      - MP_ACCESS_TOKEN
    Opcionais:
      - MP_INTEGRATOR_ID                (header x-integrator-id)
      - PUBLIC_BASE_URL                 (para montar notification_url)
      - MP_NOTIFICATION_URL             (sobrepõe a URL padrão)
      - MP_STATEMENT_DESCRIPTOR         (texto na fatura, até ~22 chars)
      - MP_MAX_INSTALLMENTS             (ex.: 3)
      - MP_VERIFY_WEBHOOK=1             (faz GET /v1/payments/{id} no parse_webhook)
      - HTTP_TIMEOUT_SECONDS            (default 15)
    """

    API_BASE = "https://api.mercadopago.com"

    def __init__(self, access_token: Optional[str] = None):
        self.token = access_token or os.getenv("MP_ACCESS_TOKEN")
        if not self.token:
            raise RuntimeError("MP_ACCESS_TOKEN não configurado")
        self.integrator_id = os.getenv("MP_INTEGRATOR_ID")
        self.timeout = float(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))

        # sessão com retry básico
        self.session = requests.Session()
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            retries = Retry(
                total=3,
                backoff_factor=0.3,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE"]),
            )
            self.session.mount("https://", HTTPAdapter(max_retries=retries))
            self.session.mount("http://", HTTPAdapter(max_retries=retries))
        except Exception:
            pass  # segue sem retry se ambiente não suportar

    # ------------------------------- utils ---------------------------------

    def _headers(self) -> Dict[str, str]:
        h = {"Authorization": f"Bearer {self.token}"}
        if self.integrator_id:
            h["x-integrator-id"] = self.integrator_id
        return h

    def _notification_url(self) -> Optional[str]:
        # prioridade: MP_NOTIFICATION_URL > PUBLIC_BASE_URL + rota padrão
        notif = os.getenv("MP_NOTIFICATION_URL")
        if notif:
            return notif
        base = os.getenv("PUBLIC_BASE_URL")
        if base:
            return f"{base.rstrip('/')}/pagamentos/webhook/mercadopago"
        return None

    @staticmethod
    def _extract_proposta_id(description: str) -> Optional[str]:
        # tenta capturar "proposta <prop_xxxxxxxxxxxx>" do texto padrão
        m = re.search(r"(prop_[0-9a-fA-F]{12})", description or "")
        return m.group(1) if m else None

    # ------------------------------- API -----------------------------------

    def create_checkout(
        self,
        *,
        amount_centavos: int,
        currency: str,
        description: str,
        success_url: str,
        cancel_url: str,
        customer: Dict[str, Any] | None = None,
    ) -> CheckoutResult:
        """
        Cria uma Preference (Checkout Pro) e retorna a URL de pagamento.
        """
        url = f"{self.API_BASE}/checkout/preferences"
        headers = self._headers()

        amount = round(int(amount_centavos) / 100.0, 2)
        max_installments = int(os.getenv("MP_MAX_INSTALLMENTS", "3"))
        statement = os.getenv("MP_STATEMENT_DESCRIPTOR")
        notification_url = self._notification_url()

        payer: Dict[str, Any] = {}
        if customer:
            # Campos aceitos: email, name, surname, phone, identification, address
            # Mantemos apenas os que vierem preenchidos
            for k in ("name", "surname", "email"):
                if customer.get(k):
                    payer[k] = customer[k]
            if customer.get("phone"):
                payer["phone"] = customer["phone"]
            if customer.get("identification"):
                payer["identification"] = customer["identification"]
            if customer.get("address"):
                payer["address"] = customer["address"]

        metadata = {
            # ajuda a reconciliar no webhook ou em consultas posteriores
            "proposta_id": self._extract_proposta_id(description),
            "context": "honorarios_proposta",
        }

        body: Dict[str, Any] = {
            "items": [
                {
                    "title": (description or "Serviço jurídico")[:120],
                    "quantity": 1,
                    "unit_price": amount,
                    "currency_id": currency.upper(),
                }
            ],
            "back_urls": {
                "success": success_url,
                "failure": cancel_url,
                "pending": cancel_url,
            },
            "auto_return": "approved",
            "binary_mode": True,  # aprova ou rejeita (evita “pendente” por muito tempo)
            "payment_methods": {
                # você pode excluir métodos indesejados adicionando "excluded_payment_types"
                "installments": max_installments,
            },
            "metadata": metadata,
        }

        if payer:
            body["payer"] = payer
        if notification_url:
            body["notification_url"] = notification_url
        if statement:
            body["statement_descriptor"] = statement[:22]

        resp = self.session.post(url, json=body, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        js = resp.json()

        # Preferimos 'init_point' (produção) mas aceitamos 'sandbox_init_point'
        checkout = js.get("init_point") or js.get("sandbox_init_point")
        provider_payment_id = str(js.get("id") or js.get("collector_id") or "")

        if not checkout:
            raise RuntimeError(f"MercadoPago: resposta sem checkout URL: {js}")

        return CheckoutResult(
            checkout_url=checkout,
            provider_payment_id=provider_payment_id or None,
            raw=js,
        )

    # ----------------------------------------------------------------------

    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normaliza diferentes formatos de webhook do MP.
        Retorna: {"status": "paid"|"failed"|"pending", "provider_payment_id": str|None, "paid_at": str|None}
        - Se MP_VERIFY_WEBHOOK=1, tenta consultar /v1/payments/{id} para confirmar status.
        """
        status = "pending"
        paid_at = None
        provider_payment_id: Optional[str] = None

        # Formatos comuns:
        # 1) { "type": "payment", "data": { "id": "12345" } }
        if isinstance(payload.get("data"), dict) and payload.get("type") in {"payment", "payments"}:
            provider_payment_id = str(payload["data"].get("id") or "")

        # 2) { "action": "payment.created", "data": { "id": "12345" } }
        if not provider_payment_id and isinstance(payload.get("data"), dict) and "payment" in str(payload.get("action", "")):
            provider_payment_id = str(payload["data"].get("id") or "")

        # 3) às vezes vem um "id" solto, ou "resource": "https://api.mercadopago.com/v1/payments/1234"
        if not provider_payment_id:
            if payload.get("id") and str(payload.get("id")).isdigit():
                provider_payment_id = str(payload.get("id"))
            elif isinstance(payload.get("resource"), str):
                m = re.search(r"/payments/(\d+)", payload["resource"])
                if m:
                    provider_payment_id = m.group(1)

        # 4) alguns webhooks trazem status direto
        raw_status = (
            payload.get("status")
            or (payload.get("data") or {}).get("status")
            or (payload.get("payment") or {}).get("status")
        )
        if raw_status:
            status = self._map_status(str(raw_status))

        # Verificação opcional no endpoint de pagamentos (recomendado)
        if os.getenv("MP_VERIFY_WEBHOOK", "0") in {"1", "true", "True"} and provider_payment_id:
            try:
                p = self._get_payment(provider_payment_id)
                if p:
                    mapped = self._map_status(str(p.get("status")))
                    if mapped:
                        status = mapped
                    # paid_at pode vir em "date_approved"
                    paid_at = p.get("date_approved") or paid_at
            except Exception:
                # Mantém status inferido
                pass

        return {
            "status": status,
            "provider_payment_id": provider_payment_id,
            "paid_at": paid_at,
        }

    # ----------------------------- helpers ---------------------------------

    def _get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """
        GET /v1/payments/{id} — útil para confirmar um status.
        """
        url = f"{self.API_BASE}/v1/payments/{payment_id}"
        resp = self.session.get(url, headers=self._headers(), timeout=self.timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _map_status(s: str) -> str:
        s = (s or "").lower().strip()
        if s in {"approved", "paid"}:
            return "paid"
        if s in {"rejected", "cancelled", "canceled"}:
            return "failed"
        # 'authorized', 'in_process', 'pending', 'in_mediation', etc.
        return "pending"