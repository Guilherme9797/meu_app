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

def test_responder_composed_greeting(monkeypatch):
    """Cumprimentos como 'ola boa noite' devem ser tratados como greeting only."""
    svc, called = _service(monkeypatch)
    resp = svc.responder("ola boa noite")
    assert resp.lower().startswith("ol")
    assert called["web"] is False

def test_responder_medium_greeting(monkeypatch):
    svc, called = _service(monkeypatch)
    svc.conf.greeting_mode = "llm"
    resp = svc.responder("ola boa noite tudo bem")
    assert resp == "ok"
    assert called["web"] is False

def test_responder_low_signal_skips_web(monkeypatch):
    svc, called = _service(monkeypatch)
    resp = svc.responder("aluguel atrasado?")
    assert "Diagnóstico" in resp
    assert called["web"] is False


def test_legal_query_boost(monkeypatch):
    svc, _ = _service(monkeypatch)
    seeds = svc._legal_query_boost("bateram meu carro")
    assert "acidente de trânsito" in seeds


def test_looks_like_juris(monkeypatch):
    svc, _ = _service(monkeypatch)
    assert svc._looks_like_juris("Ementa: algo")
    assert not svc._looks_like_juris("texto comum")


def test_responder_legal_hits_skip_generic(monkeypatch):
    svc, called = _service(monkeypatch)
    chunk = type("C", (), {"text": "Ementa: teste", "source": "http://ex"})()
    monkeypatch.setattr(svc, "_web_search_law", lambda text, k: [chunk])
    resp = svc.responder("tive um acidente de trânsito")
    assert called["web"] is False
    assert resp.strip().startswith("ok")


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


def test_penal_detect_and_tags(monkeypatch):
    svc, _ = _service(monkeypatch)
    paths = svc._penal_detect_paths("fui vítima de calúnia e difamação")
    assert any(p.endswith("calunia") for p in paths)
    tags = svc._penal_tags_from_paths(paths)
    assert "penal_calunia" in tags


def test_expand_with_legal_synonyms_penal(monkeypatch):
    svc, _ = _service(monkeypatch)
    expanded = svc._expand_with_legal_synonyms(["injúria"], ["penal_injuria"])
    assert any("injúria art 140" in q for q in expanded)

def test_dpp_detect_and_tags(monkeypatch):
    svc, _ = _service(monkeypatch)
    paths = svc._dpp_detect_paths("prisão em flagrante e audiência de custódia")
    assert any(p.endswith("prisao_em_flagrante") for p in paths)
    tags = svc._dpp_tags_from_paths(paths)
    assert "dpp_prisao_em_flagrante" in tags


def test_expand_with_legal_synonyms_dpp(monkeypatch):
    svc, _ = _service(monkeypatch)
    expanded = svc._expand_with_legal_synonyms(["prisão preventiva"], ["dpp_prisao_preventiva"])
    assert any("fumus commissi delicti" in q for q in expanded)


class SeqLLM:
    def __init__(self):
        self.calls = 0

    def generate(self, messages, temperature=0.2, max_tokens=900):
        self.calls += 1
        if self.calls == 1:
            return "sem referencia"
        return "com [S1]"


class SingleChunk:
    text = "algo"
    source = "data/pdfs/test.pdf"


class SingleRetriever:
    def retrieve(self, query, k):
        return [SingleChunk()]


def test_responder_repump_adds_sref(monkeypatch):
    llm = SeqLLM()
    svc = AtendimentoService(
        sess_repo=None,
        msg_repo=None,
        retriever=SingleRetriever(),
        tavily=None,
        llm=llm,
        conf=AtendimentoConfig(),
    )
    monkeypatch.setattr(svc, "_safe_web_search", lambda q: "")
    resp = svc.responder("pergunta")
    assert "[S1]" in resp
    assert llm.calls == 2

class StubbornLLM:
    def generate(self, messages, temperature=0.2, max_tokens=900):
        return "sempre sem referencia"


def test_responder_inserts_min_sref_when_missing(monkeypatch):
    svc = AtendimentoService(
        sess_repo=None,
        msg_repo=None,
        retriever=SingleRetriever(),
        tavily=None,
        llm=StubbornLLM(),
        conf=AtendimentoConfig(),
    )
    monkeypatch.setattr(svc, "_safe_web_search", lambda q: "")
    resp = svc.responder("pergunta")
    assert resp.endswith("[S1]")


def test_emp_detect_and_tags(monkeypatch):
    svc, _ = _service(monkeypatch)
    paths = svc._emp_detect_paths("quero abrir uma sociedade limitada com contrato social")
    assert any(p.endswith("sociedade_limitada") for p in paths)
    tags = svc._emp_tags_from_paths(paths)
    assert "emp_sociedade_limitada" in tags


def test_expand_with_legal_synonyms_emp(monkeypatch):
    svc, _ = _service(monkeypatch)
    expanded = svc._expand_with_legal_synonyms(["sociedade limitada"], ["emp_sociedade_limitada"])
    assert any("contrato social" in q for q in expanded)


def test_prev_detect_and_tags(monkeypatch):
    svc, _ = _service(monkeypatch)
    paths = svc._prev_detect_paths("aposentadoria por idade no INSS")
    assert any(p.endswith("aposentadoria_por_idade") for p in paths)
    tags = svc._prev_tags_from_paths(paths)
    assert "prev_aposentadoria_por_idade" in tags


def test_expand_with_legal_synonyms_prev(monkeypatch):
    svc, _ = _service(monkeypatch)
    expanded = svc._expand_with_legal_synonyms(["aposentadoria por idade"], ["prev_aposentadoria_por_idade"])
    assert any("idade mínima" in q for q in expanded)

def test_amb_detect_and_tags(monkeypatch):
    svc, _ = _service(monkeypatch)
    paths = svc._amb_detect_paths("licenciamento ambiental para obra")
    assert any(p.endswith("licenciamento_ambiental") for p in paths)
    tags = svc._amb_tags_from_paths(paths)
    assert "amb_licenciamento_ambiental" in tags


def test_expand_with_legal_synonyms_amb(monkeypatch):
    svc, _ = _service(monkeypatch)
    expanded = svc._expand_with_legal_synonyms(["licenciamento ambiental"], ["amb_licenciamento_ambiental"])
    assert any("LP LI LO" in q for q in expanded)