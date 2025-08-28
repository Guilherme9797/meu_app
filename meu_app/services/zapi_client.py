from __future__ import annotations
import os
from typing import Optional, Dict, Any
import requests


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
    ):
        # normaliza variáveis de ambiente (remove espaços/linhas)
        self.base_url = (base_url or os.getenv("ZAPI_BASE_URL", "https://api.z-api.io")).strip().rstrip("/")
        self.instance_id = (instance_id or os.getenv("ZAPI_INSTANCE_ID", "")).strip() or None
        self.token = (token or os.getenv("ZAPI_INSTANCE_TOKEN", "")).strip() or None
        self.client_token = (client_token or os.getenv("ZAPI_CLIENT_TOKEN", "")).strip() or None

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
