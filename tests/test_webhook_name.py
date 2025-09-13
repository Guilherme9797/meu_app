import importlib

import pytest

from types import SimpleNamespace


def test_webhook_asks_and_stores_name(tmp_path, monkeypatch):
    db_file = tmp_path / "db.sqlite"
    monkeypatch.setenv("APP_DB_PATH", str(db_file))

    srv = importlib.reload(importlib.import_module("server"))

    class DummyZapi:
        def __init__(self):
            self.sent = []

        def parse_incoming(self, data):
            from meu_app.services.zapi_client import NormalizedMessage
            text = data.get("text", {})
            if isinstance(text, dict):
                msg = text.get("message")
            else:
                msg = text
            return NormalizedMessage(client_id=data.get("phone"), text=msg, msg_id="1", timestamp="1")

        def send_message(self, phone, message):
            self.sent.append((phone, message))

    dummy = DummyZapi()
    monkeypatch.setattr(srv, "zapi_client", dummy)
    monkeypatch.setattr(srv, "atendimento_service", SimpleNamespace(handle_incoming=lambda p, t: "ok"))

    client = srv.app.test_client()

    payload1 = {"type": "ReceivedCallback", "phone": "123", "text": {"message": "Olá"}}
    resp1 = client.post("/zapi/webhook/received", json=payload1)
    assert resp1.status_code == 200
    assert dummy.sent and "Qual é o seu nome" in dummy.sent[0][1]

    payload2 = {"type": "ReceivedCallback", "phone": "123", "text": {"message": "Guilherme"}}
    resp2 = client.post("/zapi/webhook/received", json=payload2)
    assert resp2.status_code == 200
    assert any("Guilherme" in msg for _, msg in dummy.sent)

    from meu_app.persistence.repositories import ContatoRepository
    repo = ContatoRepository()
    ctt = repo.get_by_phone("123")
    assert ctt["nome"] == "Guilherme"