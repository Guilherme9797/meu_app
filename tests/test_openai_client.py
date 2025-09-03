from meu_app.utils.openai_client import OpenAIClient
import meu_app.utils.openai_client as oc


class DummyOpenAI:
    def __init__(self, *args, **kwargs):
        self.chat = self
        self.completions = self
        self.last_params = None

    def create(self, **params):
        self.last_params = params
        class Choice:
            message = type("msg", (), {"content": "ok"})
        return type("Resp", (), {"choices": [Choice()]})()


class DummyTokensUnsupported:
    def __init__(self, *args, **kwargs):
        self.chat = self
        self.completions = self
        self.calls = []

    def create(self, **params):
        self.calls.append(params)
        if "max_tokens" in params:
            raise Exception(
                "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead."
            )
        class Choice:
            message = type("msg", (), {"content": "ok"})
        return type("Resp", (), {"choices": [Choice()]})()


class DummyTempUnsupported:
    def __init__(self, *args, **kwargs):
        self.chat = self
        self.completions = self
        self.calls = []

    def create(self, **params):
        self.calls.append(params)
        if params.get("temperature") not in (None, 1.0):
            raise Exception(
                "Unsupported value: 'temperature' does not support 0.2 with this model. Only the default (1) value is supported."
            )
        class Choice:
            message = type("msg", (), {"content": "ok"})
        return type("Resp", (), {"choices": [Choice()]})()

class DummyBadModel:
    def __init__(self, *args, **kwargs):
        self.chat = self
        self.completions = self
        self.calls = []

    def create(self, **params):
        self.calls.append(params)
        if len(self.calls) == 1:
            raise oc.BadRequestError("bad request")
        class Choice:
            message = type("msg", (), {"content": "ok"})
        return type("Resp", (), {"choices": [Choice()]})()


def test_default_temperature_omitted(monkeypatch):
    monkeypatch.setattr(oc, "OpenAI", DummyOpenAI)
    client = OpenAIClient(api_key="x", chat_model="gpt")
    resp = client.chat("sys", "usr")
    assert resp == "ok"
    assert "temperature" not in client.client.last_params


def test_custom_temperature_forwarded(monkeypatch):
    monkeypatch.setattr(oc, "OpenAI", DummyOpenAI)
    client = OpenAIClient(api_key="x", chat_model="gpt", temperature=0.5)
    client.chat("sys", "usr")
    assert client.client.last_params["temperature"] == 0.5


def test_chat_fallback_to_max_completion_tokens(monkeypatch):
    monkeypatch.setattr(oc, "OpenAI", DummyTokensUnsupported)
    client = OpenAIClient(api_key="x", chat_model="gpt")
    resp = client.chat("sys", "usr", extra={"max_tokens": 77})
    assert resp == "ok"
    calls = client.client.calls
    assert calls[0]["max_tokens"] == 77
    assert calls[1]["max_completion_tokens"] == 77


def test_chat_temperature_fallback(monkeypatch):
    monkeypatch.setattr(oc, "OpenAI", DummyTempUnsupported)
    client = OpenAIClient(api_key="x", chat_model="gpt")
    resp = client.chat("sys", "usr", extra={"temperature": 0.2})
    assert resp == "ok"
    calls = client.client.calls
    assert calls[0]["temperature"] == 0.2
    assert "temperature" not in calls[1]


def test_chat_model_fallback(monkeypatch):
    monkeypatch.setattr(oc, "OpenAI", DummyBadModel)
    monkeypatch.setattr(oc, "BadRequestError", type("BadRequestError", (Exception,), {}))
    client = OpenAIClient(api_key="x", chat_model="bad-model")
    resp = client.chat("sys", "usr")
    assert resp == "ok"
    calls = client.client.calls
    assert calls[0]["model"] == "bad-model"
    assert calls[1]["model"] == "gpt-5-mini"