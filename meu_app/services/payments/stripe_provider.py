# meu_app/services/payments/stripe_provider.py
from __future__ import annotations
import os
import re
import requests
from typing import Dict, Any, Optional

from .base import PaymentProvider, CheckoutResult


class StripeProvider(PaymentProvider):
    """
    Stripe – Checkout Sessions (pagamento único).
    Requer:
      - STRIPE_API_KEY
    Opcionais:
      - HTTP_TIMEOUT_SECONDS (default 15)
      - STRIPE_STATEMENT_DESCRIPTOR  (até 22 chars)
      - STRIPE_PAYMENT_METHOD_TYPES  (ex.: "card,pix")   # depende da região/habilitação
      - STRIPE_ALLOW_PROMO_CODES     ("1"/"0"; default 0)
      - STRIPE_PHONE_COLLECTION      ("1"/"0"; default 1)
      - STRIPE_BILLING_ADDR          ("auto"|"required"; default "auto")
      - STRIPE_AUTOMATIC_TAX         ("1"/"0"; default 0)
      - PUBLIC_BASE_URL  (para montar success/cancel se o orquestrador não passar)
      - STRIPE_VERIFY_WEBHOOK        ("1"/"0"; default 0)  # validar via GET /v1/events/{id}
    """

    API_BASE = "https://api.stripe.com"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("STRIPE_API_KEY")
        if not self.api_key:
            raise RuntimeError("STRIPE_API_KEY não configurada")
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
                allowed_methods=frozenset(["GET", "POST", "DELETE"]),
            )
            self.session.mount("https://", HTTPAdapter(max_retries=retries))
            self.session.mount("http://", HTTPAdapter(max_retries=retries))
        except Exception:
            pass  # segue sem retry se não disponível

    # ------------------------------ utils ---------------------------------

    @staticmethod
    def _extract_proposta_id(desc: str) -> Optional[str]:
        # procura padrão prop_xxxxxxxxxxxx
        m = re.search(r"(prop_[0-9a-fA-F]{12})", desc or "")
        return m.group(1) if m else None

    def _auth(self):
        # Basic Auth: chave como usuário, senha vazia
        return (self.api_key, "")

    # ------------------------------- API ----------------------------------

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
        Cria uma Checkout Session e retorna a URL.
        - A Stripe exige form-urlencoded para /v1/checkout/sessions.
        """
        url = f"{self.API_BASE}/v1/checkout/sessions"

        # Configs por ambiente
        descriptor = os.getenv("STRIPE_STATEMENT_DESCRIPTOR")
        pm_types = [s.strip() for s in os.getenv("STRIPE_PAYMENT_METHOD_TYPES", "card").split(",") if s.strip()]
        allow_promo = os.getenv("STRIPE_ALLOW_PROMO_CODES", "0") in {"1", "true", "True"}
        phone_collect = os.getenv("STRIPE_PHONE_COLLECTION", "1") in {"1", "true", "True"}
        billing_addr = os.getenv("STRIPE_BILLING_ADDR", "auto")  # "auto" | "required"
        automatic_tax = os.getenv("STRIPE_AUTOMATIC_TAX", "0") in {"1", "true", "True"}

        # URLs de fallback (caso o orquestrador tenha passado vazio)
        base = os.getenv("PUBLIC_BASE_URL")
        if not success_url and base:
            success_url = f"{base.rstrip('/')}/pagamento/sucesso?session_id={{CHECKOUT_SESSION_ID}}"
        if not cancel_url and base:
            cancel_url = f"{base.rstrip('/')}/pagamento/cancelado"

        # Metadata útil (reconciliação interna)
        metadata = {
            "proposta_id": self._extract_proposta_id(description or ""),
            "context": "honorarios_proposta",
        }

        # Campos do comprador (opcionais)
        customer_email = None
        if customer:
            customer_email = customer.get("email")

        # Monta payload (x-www-form-urlencoded)
        data: Dict[str, Any] = {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "locale": "pt-BR",

            # item único
            "line_items[0][price_data][currency]": (currency or "brl").lower(),
            "line_items[0][price_data][product_data][name]": (description or "Serviço jurídico")[:120],
            "line_items[0][price_data][unit_amount]": int(amount_centavos),
            "line_items[0][quantity]": 1,

            # preferências de coleta
            "billing_address_collection": billing_addr,
            "allow_promotion_codes": "true" if allow_promo else "false",
            "phone_number_collection[enabled]": "true" if phone_collect else "false",

            # impostos automáticos (se habilitado na conta)
            "automatic_tax[enabled]": "true" if automatic_tax else "false",
        }

        # Tipos de pagamento (Stripe requer formato payment_method_types[])
        for i, pm in enumerate(pm_types):
            data[f"payment_method_types[{i}]"] = pm

        # Statement descriptor (máx ~22 chars)
        if descriptor:
            data["payment_intent_data[statement_descriptor]"] = descriptor[:22]

        # Metadata
        for k, v in metadata.items():
            if v is not None:
                data[f"metadata[{k}]"] = str(v)

        # E-mail do cliente
        if customer_email:
            data["customer_email"] = customer_email

        # Recomenda-se appending do session id na success_url (caso não esteja)
        if "{CHECKOUT_SESSION_ID}" not in (success_url or ""):
            data["success_url"] = (success_url or "") + ("&" if "?" in success_url else "?") + "session_id={CHECKOUT_SESSION_ID}"

        # Cria sessão
        resp = self.session.post(url, data=data, auth=self._auth(), timeout=self.timeout)
        resp.raise_for_status()
        js = resp.json()

        # Retorno principal
        return CheckoutResult(
            checkout_url=js.get("url"),
            provider_payment_id=js.get("id"),  # cs_...
            raw=js,
        )

    # ----------------------------------------------------------------------

    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normaliza os eventos do Stripe em {"status", "provider_payment_id", "paid_at"}.
        Priorizamos eventos "checkout.session.completed" para casar com o provider_payment_id (cs_...).
        """
        status = "pending"
        provider_payment_id: Optional[str] = None
        paid_at: Optional[str] = None

        evt_type = payload.get("type")
        obj = (payload.get("data") or {}).get("object") or {}

        # 1) Evento do Checkout Session (ideal – casa com cs_... salvo ao criar)
        if evt_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
            provider_payment_id = obj.get("id")  # cs_...
            sess_status = (obj.get("payment_status") or "").lower()
            if sess_status in {"paid"} or evt_type == "checkout.session.completed":
                status = "paid"
            elif sess_status in {"unpaid"}:
                status = "failed"
            else:
                status = "pending"

        # 2) Fallback: eventos de Payment Intent
        elif evt_type in {"payment_intent.succeeded"}:
            status = "paid"
            # não temos cs_ aqui — o server pode não localizar. Mantemos None.
        elif evt_type in {"payment_intent.payment_failed"}:
            status = "failed"

        # 3) Outro fallback: Charge
        elif evt_type in {"charge.succeeded"}:
            status = "paid"
        elif evt_type in {"charge.failed"}:
            status = "failed"

        # Verificação opcional no endpoint de eventos (recomendado em produção)
        if os.getenv("STRIPE_VERIFY_WEBHOOK", "0") in {"1", "true", "True"}:
            try:
                evt_id = payload.get("id")
                if evt_id:
                    e = self._get_event(evt_id)
                    if e:
                        _type = e.get("type")
                        _obj = (e.get("data") or {}).get("object") or {}
                        # re-aplica lógica (pode preencher provider_payment_id com mais certeza)
                        if _type.startswith("checkout.session."):
                            provider_payment_id = _obj.get("id") or provider_payment_id
                            sess_status = (_obj.get("payment_status") or "").lower()
                            if sess_status == "paid":
                                status = "paid"
            except Exception:
                # segue com o inferido
                pass

        return {
            "status": status,
            "provider_payment_id": provider_payment_id,
            "paid_at": paid_at,
        }

    # ----------------------------- helpers ---------------------------------

    def _get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        GET /v1/events/{id} – útil para confirmação de webhook quando STRIPE_VERIFY_WEBHOOK=1.
        """
        url = f"{self.API_BASE}/v1/events/{event_id}"
        resp = self.session.get(url, auth=self._auth(), timeout=self.timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()