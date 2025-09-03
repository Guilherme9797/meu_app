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


class EmptyLLM:
    def generate(self, messages, temperature=0.2, max_tokens=900):
        return ""


def test_fallback_infers_from_text(monkeypatch):
    svc = AtendimentoService(
        sess_repo=None,
        msg_repo=None,
        retriever=DummyRetriever(),
        tavily=None,
        llm=EmptyLLM(),
        conf=AtendimentoConfig(),
    )
    monkeypatch.setattr(svc, "_safe_web_search", lambda q: "")
    resp = svc.responder(
        "divulgaram uma imagem minha na rede social com a frase: me paga caloteiro"
    )
    assert "tema civel" in resp.lower()


class PenalChunk:
    text = "dummy"
    source = "data/pdfs/penal_especial/test.pdf"


class PenalRetriever:
    def retrieve(self, query, k):
        return [PenalChunk()]


def test_fallback_infers_from_chunks(monkeypatch):
    svc = AtendimentoService(
        sess_repo=None,
        msg_repo=None,
        retriever=PenalRetriever(),
        tavily=None,
        llm=EmptyLLM(),
        conf=AtendimentoConfig(),
    )
    monkeypatch.setattr(svc, "_safe_web_search", lambda q: "")
    resp = svc.responder("fui acusado de furto em uma loja")
    assert "tema penal" in resp.lower()