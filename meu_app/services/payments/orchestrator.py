# meu_app/services/payments/orchestrator.py
from __future__ import annotations
import os
from typing import Dict, Any, Optional

from .base import PaymentProvider, CheckoutResult
from .stripe_provider import StripeProvider
from .mercadopago_provider import MercadoPagoProvider


class PaymentOrchestrator:
    """
    Orquestrador de pagamentos.
    - Seleciona o provedor com base em PAYMENTS_PROVIDER (ou parâmetro do __init__).
    - Cria checkout (link de pagamento) delegando para o provider.
    - Normaliza webhooks via provider.parse_webhook(...).

    Dica: passe `proposta_id` e `payment_id` para que o orquestrador
    injete essas referências no `description`. Os providers já extraem `prop_...`
    do description e setam `metadata` apropriado.
    """

    def __init__(self, provider_name: Optional[str] = None):
        self.name = (provider_name or os.getenv("PAYMENTS_PROVIDER", "mercadopago")).strip().lower()
        self.provider: PaymentProvider = self._make_provider(self.name)

    # ------------------------------------------------------------------ #
    # Factory
    # ------------------------------------------------------------------ #
    @staticmethod
    def _make_provider(name: str) -> PaymentProvider:
        if name == "stripe":
            return StripeProvider()
        if name == "mercadopago":
            return MercadoPagoProvider()
        raise RuntimeError(f"Provider desconhecido: {name!r}. Use 'stripe' ou 'mercadopago'.")

    @staticmethod
    def available_providers() -> Dict[str, str]:
        return {"stripe": "Stripe Checkout Session", "mercadopago": "Mercado Pago Checkout Pro"}

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decorate_description(desc: Optional[str], *, proposta_id: Optional[str], payment_id: Optional[str]) -> str:
        """
        Garante que o description contenha tokens internos para reconciliação:
          - prop_xxxxxxxxxxxx
          - pay_xxxxxxxxxxxx
        (Os providers já tentam extrair prop_... do description e setam metadata.)
        """
        base = (desc or "Serviço jurídico").strip()
        suffix_parts = []
        if proposta_id and "prop_" not in base:
            suffix_parts.append(proposta_id)
        if payment_id and "pay_" not in base:
            suffix_parts.append(payment_id)
        if suffix_parts:
            # adiciona em forma legível e compacta
            base = f"{base} [{' | '.join(suffix_parts)}]"
        return base[:120]  # limites típicos de título/descrição

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def create_checkout(
        self,
        *,
        amount_centavos: int,
        description: str,
        success_url: str,
        cancel_url: str,
        currency: str = "BRL",
        customer: Dict[str, Any] | None = None,
        proposta_id: Optional[str] = None,
        payment_id: Optional[str] = None,
    ) -> CheckoutResult:
        """
        Cria o link de pagamento no provider selecionado.
        - Injeta `prop_...` e `pay_...` no description (para conciliação nos webhooks).
        - `customer` pode incluir email/name/etc. conforme suporte do provider.
        """
        safe_desc = self._decorate_description(description, proposta_id=proposta_id, payment_id=payment_id)
        return self.provider.create_checkout(
            amount_centavos=int(amount_centavos),
            currency=currency,
            description=safe_desc,
            success_url=success_url,
            cancel_url=cancel_url,
            customer=customer or {},
        )

    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normaliza o webhook em:
          {"status": "paid"|"failed"|"pending", "provider_payment_id": str|None, "paid_at": str|None}
        """
        return self.provider.parse_webhook(payload)