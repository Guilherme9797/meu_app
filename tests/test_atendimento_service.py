import pytest
from meu_app.services.atendimento_service import AtendimentoService, AtendimentoConfig


class DummyRetriever:
    def retrieve(self, query, k):
        return []


class DummyLLM:
    def generate(self, messages, temperature=0.2, max_tokens=900):
        return "ok"


def _service(monkeypatch):
    svc = AtendimentoService(
        sess_repo=None,
        msg_repo=None,
        retriever=DummyRetriever(),
        tavily=None,
        llm=DummyLLM(),
        conf=AtendimentoConfig(),
    )
    called = {"web": False}

    def fake_web(q):
        called["web"] = True
        return "web"

    monkeypatch.setattr(svc, "_safe_web_search", fake_web)
    return svc, called


def test_responder_greeting_skips_web(monkeypatch):
    svc, called = _service(monkeypatch)
    resp = svc.responder("oi")
    assert resp.lower().startswith("ol")
    assert called["web"] is False


def test_responder_low_signal_skips_web(monkeypatch):
    svc, called = _service(monkeypatch)
    resp = svc.responder("aluguel atrasado?")
    assert resp == "ok"
    assert called["web"] is False