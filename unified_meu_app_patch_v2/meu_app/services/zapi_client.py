import os
import requests
from typing import Optional, Dict, Any

class ZapiClient:
    """Cliente simples para a Z-API (WhatsApp)."""
    def __init__(self, instance_id: Optional[str] = None, token: Optional[str] = None, base_url: Optional[str] = None):
        self.instance_id = instance_id or os.getenv("ZAPI_INSTANCE_ID")
        self.token = token or os.getenv("ZAPI_TOKEN") or os.getenv("ZAPI_CLIENT_TOKEN")
        self.base_url = (base_url or os.getenv("ZAPI_BASE_URL") or "https://api.z-api.io").rstrip("/")
        if not self.instance_id or not self.token:
            raise ValueError("ZAPI_INSTANCE_ID e ZAPI_TOKEN (ou ZAPI_CLIENT_TOKEN) são obrigatórios.")

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url}/instances/{self.instance_id}/token/{self.token}/{endpoint.lstrip('/')}"

    def send_text(self, phone: str, text: str, message_id_to_reply: Optional[str] = None, reply_to_message_id: Optional[str] = None) -> Dict[str, Any]:
        url = self._url("send-text")
        payload = {"phone": phone, "message": text}
        thread_id = reply_to_message_id or message_id_to_reply
        if thread_id:
            payload["messageId"] = thread_id
        r = requests.post(url, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def send_document(self, phone: str, document_url_or_b64: str, extension: str) -> Dict[str, Any]:
        url = self._url(f"send-document/{extension}")
        payload = {"phone": phone, "document": document_url_or_b64}
        r = requests.post(url, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()

    def update_webhook_received(self, webhook_url: str) -> Dict[str, Any]:
        url = self._url("update-webhook-received")
        r = requests.put(url, json={"webhookUrl": webhook_url}, timeout=30)
        r.raise_for_status()
        return r.json()

    def update_webhook_delivery(self, webhook_url: str) -> Dict[str, Any]:
        url = self._url("update-webhook-delivery")
        r = requests.put(url, json={"webhookUrl": webhook_url}, timeout=30)
        r.raise_for_status()
        return r.json()
