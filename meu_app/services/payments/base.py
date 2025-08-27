# meu_app/services/payments/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, Mapping

JSONDict = Dict[str, Any]


# ----------------------------- Tipos & Enums -----------------------------

class PaymentStatus(str, Enum):
    """Status normalizado para pagamentos."""
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    EXPIRED = "expired"
    REFUNDED = "refunded"


@dataclass
class CheckoutResult:
    """
    Resultado de criação de checkout/link de pagamento.
    - checkout_url: URL para o cliente concluir o pagamento
    - provider_payment_id: identificador principal do provider (ex.: cs_... no Stripe; id/collector no MP)
    - raw: payload bruto retornado pelo provider (útil para auditoria/debug)
    """
    checkout_url: str
    provider_payment_id: Optional[str] = None
    raw: Optional[JSONDict] = None


@dataclass
class WebhookResult:
    """
    Resultado normalizado de um webhook de pagamento.
    Use .to_dict() se quiser compatibilidade direta com quem espera dict.
    """
    status: PaymentStatus
    provider_payment_id: Optional[str] = None
    paid_at: Optional[str] = None  # ISO-8601 UTC quando o provider informar

    def to_dict(self) -> JSONDict:
        return {
            "status": self.status.value,
            "provider_payment_id": self.provider_payment_id,
            "paid_at": self.paid_at,
        }


# ----------------------------- Exceptions -----------------------------

class PaymentError(Exception):
    """Erro genérico no fluxo de pagamento."""


class ProviderConfigError(PaymentError):
    """Configuração ausente/inválida do provider (ex.: credenciais)."""


class ProviderHTTPError(PaymentError):
    """Erro HTTP ao chamar o provider (status >= 400)."""
    def __init__(self, status_code: int, message: str, payload: Optional[JSONDict] = None):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.payload = payload or {}


# ----------------------------- Helpers comuns -----------------------------

def ensure_positive_cents(amount_centavos: int) -> int:
    """
    Garante que o valor em centavos é um inteiro positivo.
    Levanta ValueError se inválido.
    """
    try:
        v = int(amount_centavos)
    except Exception as e:
        raise ValueError("amount_centavos deve ser inteiro (centavos).") from e
    if v <= 0:
        raise ValueError("amount_centavos deve ser > 0 (centavos).")
    return v


def normalize_currency(code: str) -> str:
    """
    Normaliza código de moeda para ISO-4217 em minúsculas onde necessário (providers aceitam variações).
    Mantemos em maiúsculas para exibir/armazenar (compatível com BRL).
    """
    if not code:
        return "BRL"
    code = str(code).strip().upper()
    if len(code) != 3:
        raise ValueError(f"Código de moeda inválido: {code!r}")
    return code


def safe_truncate(text: str, max_len: int) -> str:
    """Corta texto com segurança para limites de providers (ex.: 120 chars)."""
    t = (text or "").strip()
    return t if len(t) <= max_len else (t[: max_len - 1] + "…")


# ----------------------------- Interface Base -----------------------------

class PaymentProvider(ABC):
    """
    Interface base para providers de pagamento.
    Implementações: StripeProvider, MercadoPagoProvider, etc.
    """

    @abstractmethod
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
        Cria um link/checkout de pagamento no provider.
        Deve retornar um CheckoutResult com a URL para o cliente pagar.
        """
        raise NotImplementedError

    @abstractmethod
    def parse_webhook(self, payload: JSONDict) -> JSONDict:
        """
        Normaliza o webhook do provider em um dict:
            {
              "status": "paid" | "failed" | "pending" | "expired" | "refunded",
              "provider_payment_id": str | None,
              "paid_at": str | None,   # ISO-8601 UTC, se disponível
            }
        Dica: você pode criar um WebhookResult e retornar `WebhookResult(...).to_dict()`.
        """
        raise NotImplementedError

    # --- Opcional: validação de assinatura ---
    def verify_signature(self, headers: Mapping[str, str], body: bytes) -> bool:
        """
        Hook opcional para validação de assinatura do webhook (quando o provider suportar).
        Implementações podem sobrescrever. Por padrão, retorna True.
        """
        return True