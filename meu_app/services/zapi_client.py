from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Literal

import requests


MediaType = Literal["audio", "image", "document", "unknown"]


@dataclass
class NormalizedMessage:
    """Representa a forma canônica que usaremos internamente."""

    client_id: str
    text: Optional[str]
    msg_id: Optional[str]
    timestamp: Optional[str]
    media_type: Optional[MediaType] = None
    media_url: Optional[str] = None
    media_mime: Optional[str] = None
    media_caption: Optional[str] = None


class ZapiClient:
    """
    Cliente mínimo para a Z-API com:
      - envio de texto (send_text)
      - configuração de webhooks (recebidas e "sent by me")
    Rotas ajustadas para o padrão atual da Z-API:
      * PUT update-webhook-received        { "value": "<URL>" }
      * PUT update-every-webhooks          { "value": "<URL>", "notifySentByMe": true }
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        instance_id: Optional[str] = None,
        token: Optional[str] = None,
        client_token: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ):
        # normaliza variáveis de ambiente (remove espaços/linhas)
        self.base_url = (base_url or os.getenv("ZAPI_BASE_URL", "https://api.z-api.io")).strip().rstrip("/")
        self.instance_id = (instance_id or os.getenv("ZAPI_INSTANCE_ID", "")).strip() or None
        self.token = (token or os.getenv("ZAPI_INSTANCE_TOKEN", "")).strip() or None
        self.client_token = (client_token or os.getenv("ZAPI_CLIENT_TOKEN", "")).strip() or None
        self.webhook_secret = webhook_secret or os.getenv("ZAPI_WEBHOOK_SECRET")

        if not self.instance_id or not self.token:
            raise RuntimeError("Z-API: faltam ZAPI_INSTANCE_ID ou ZAPI_INSTANCE_TOKEN no ambiente.")

        self._headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.client_token:
            # muitas rotas exigem esse header
            self._headers["Client-Token"] = self.client_token
    @classmethod
    def from_env(cls) -> "ZapiClient":
        """Instancia o cliente lendo variáveis de ambiente padrão."""
        return cls()

    def _url(self, path: str) -> str:
        return f"{self.base_url}/instances/{self.instance_id}/token/{self.token}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Faz a chamada HTTP e **não** levanta exceção em erro HTTP.
        Retorna dict com dados ou com chaves 'error'/'status_code'/'data' em caso de erro."""
        url = self._url(path)
        try:
            r = requests.request(method.upper(), url, headers=self._headers, json=data, timeout=30)
        except requests.RequestException as e:
            return {"error": "request_exception", "detail": str(e)}

        try:
            payload = r.json()
        except ValueError:
            payload = {"text": r.text or ""}

        if r.ok:
            return payload
        # padroniza erro sem quebrar o servidor
        return {
            "error": payload.get("error") or "http_error",
            "status_code": r.status_code,
            "data": payload,
        }

    def _post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", path, data)

    # ========= usadas pelo seu app =========

    def send_text(
        self,
        phone: Optional[str],
        message: str,
        chat_id: Optional[str] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Envia texto. Informe `phone` (E.164) OU `chat_id` (ex.: 5511999999999@c.us).
        """
        if not chat_id and not phone:
            return {"error": "missing_target", "detail": "Informe phone ou chat_id."}

        payload: Dict[str, Any] = {"message": message}
        if chat_id:
            payload["chatId"] = chat_id
        else:
            payload["phone"] = phone

        # Algumas versões aceitam quotedMsgId; outras replyMessageId.
        if reply_to_message_id:
            payload["replyMessageId"] = reply_to_message_id

        return self._post("send-text", payload)

    # ====== WEBHOOKS (rotas atuais) ======

    def update_webhook_received(self, url: str) -> Dict[str, Any]:
        """
        Configura webhook de RECEBIMENTO de mensagens.
        Rota atual: PUT update-webhook-received  { "value": "<URL>" }
        """
        if not url:
            return {"error": "invalid_url", "detail": "URL do webhook (received) vazia"}
        return self._request("PUT", "update-webhook-received", {"value": url})

    def update_webhook_delivery(self, url: str) -> Dict[str, Any]:
        """
        Configura webhooks para também notificar mensagens enviadas por você (sent by me).
        Rota atual: PUT update-every-webhooks  { "value": "<URL>", "notifySentByMe": true }
        """
        if not url:
            return {"error": "invalid_url", "detail": "URL do webhook (delivery) vazia"}
        return self._request("PUT", "update-every-webhooks", {"value": url, "notifySentByMe": True})

    # (opcional) método explícito se quiser usar no admin
    def update_every_webhooks(self, url: str, notify_sent_by_me: bool = True) -> Dict[str, Any]:
        if not url:
            return {"error": "invalid_url", "detail": "URL vazia"}
        return self._request("PUT", "update-every-webhooks", {"value": url, "notifySentByMe": bool(notify_sent_by_me)})

    # -------- utilitários para webhooks ---------

    def verify_signature(self, raw_body: bytes, headers: Dict[str, str]) -> bool:
        """Confere a assinatura HMAC enviada pela Z-API."""
        if not self.webhook_secret:
            return True
        lowered = {k.lower(): v for k, v in headers.items()}
        for name in ("x-hub-signature-256", "x-zapi-signature", "x-z-api-signature"):
            provided = lowered.get(name)
            if provided:
                break
        else:
            return False
        provided_hex = provided.replace("sha256=", "").strip()
        mac = hmac.new(self.webhook_secret.encode("utf-8"), msg=raw_body, digestmod=hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, provided_hex)

    @staticmethod
    def normalize_msisdn(phone: str, default_country: str = "55") -> str:
        digits = re.sub(r"\D", "", phone or "")
        if not digits:
            raise ValueError("Telefone ausente no payload.")
        if digits.startswith(default_country):
            return f"+{digits}"
        if len(digits) in (10, 11):
            return f"+{default_country}{digits}"
        if digits.startswith("0") and digits[1:].startswith(default_country):
            return f"+{digits[1:]}"
        return f"+{digits}"

    @staticmethod
    def _extract_text(payload: Dict[str, Any]) -> Optional[str]:
        candidates = [
            ("message",),
            ("text",),
            ("data", "message"),
            ("data", "text"),
            ("messages", 0, "text", "body"),
            ("entry", 0, "changes", 0, "value", "messages", 0, "text", "body"),
        ]
        for path in candidates:
            ref: Any = payload
            try:
                for key in path:
                    ref = ref[key]
                if isinstance(ref, str) and ref.strip():
                    return ref.strip()
            except Exception:
                continue
        return None

    @staticmethod
    def _extract_phone(payload: Dict[str, Any]) -> Optional[str]:
        candidates = [
            ("phone",),
            ("from",),
            ("data", "phone"),
            ("data", "from"),
            ("messages", 0, "from"),
            ("entry", 0, "changes", 0, "value", "messages", 0, "from"),
            ("contact", "wa_id"),
        ]
        for path in candidates:
            ref: Any = payload
            try:
                for key in path:
                    ref = ref[key]
                if isinstance(ref, str) and ref.strip():
                    return ref.strip()
            except Exception:
                continue
        return None

    @staticmethod
    def _extract_msg_id(payload: Dict[str, Any]) -> Optional[str]:
        for path in [
            ("id",),
            ("data", "id"),
            ("messages", 0, "id"),
            ("entry", 0, "changes", 0, "value", "messages", 0, "id"),
        ]:
            ref: Any = payload
            try:
                for key in path:
                    ref = ref[key]
                if isinstance(ref, str) and ref.strip():
                    return ref.strip()
            except Exception:
                continue
        return None

    @staticmethod
    def _extract_timestamp(payload: Dict[str, Any]) -> Optional[str]:
        for path in [
            ("timestamp",),
            ("data", "timestamp"),
            ("messages", 0, "timestamp"),
            ("entry", 0, "changes", 0, "value", "messages", 0, "timestamp"),
        ]:
            ref: Any = payload
            try:
                for key in path:
                    ref = ref[key]
                if isinstance(ref, (int, float)):
                    return datetime.utcfromtimestamp(int(ref)).isoformat() + "Z"
                if isinstance(ref, str) and ref.strip():
                    return ref.strip()
            except Exception:
                continue
        return datetime.utcnow().isoformat() + "Z"

    @staticmethod
    def _extract_media(payload: Dict[str, Any]) -> tuple[Optional[MediaType], Optional[str], Optional[str], Optional[str]]:
        """Tenta extrair (media_type, media_url, media_mime, media_caption)."""
        for path in [("messages", 0, "image"), ("messages", 0, "audio"), ("messages", 0, "document")]:
            ref: Any = payload
            try:
                for key in path:
                    ref = ref[key]
                if isinstance(ref, dict) and ref.get("url"):
                    url = ref["url"]
                    mime = ref.get("mime_type") or ref.get("mime")
                    mtype: MediaType = "image" if "image" in path else "audio" if "audio" in path else "document"
                    caption = ref.get("caption")
                    return mtype, url, mime, caption
            except Exception:
                continue

        flat_media_url = payload.get("media_url")
        if flat_media_url:
            flat_media_type = payload.get("media_type", "unknown")
            mtype: MediaType = (
                "audio" if flat_media_type == "audio" else "image" if flat_media_type == "image" else "document" if flat_media_type == "document" else "unknown"
            )
            return mtype, flat_media_url, payload.get("mime_type") or payload.get("mimetype"), payload.get("caption")
        return None, None, None, None

    def parse_incoming(self, payload: Dict[str, Any]) -> NormalizedMessage:
        raw_phone = self._extract_phone(payload)
        text = self._extract_text(payload)
        media_type, media_url, media_mime, media_caption = self._extract_media(payload)

        if not raw_phone:
            raise ValueError("Telefone do remetente não encontrado no payload.")
        if not (text or media_url):
            raise ValueError("Conteúdo não encontrado (nem texto nem mídia).")

        client_id = self.normalize_msisdn(raw_phone)
        msg_id = self._extract_msg_id(payload)
        ts = self._extract_timestamp(payload)

        return NormalizedMessage(
            client_id=client_id,
            text=text,
            msg_id=msg_id,
            timestamp=ts,
            media_type=media_type,
            media_url=media_url,
            media_mime=media_mime,
            media_caption=media_caption,
        )