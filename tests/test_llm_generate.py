import meu_app.utils.openai_client as oc


class DummyOK:
    def __init__(self, *args, **kwargs):
        self.chat = self
        self.completions = self
        self.last_params = None

    def create(self, **params):
        self.last_params = params
        class Choice:
            message = type("msg", (), {"content": "ok"})
        return type("Resp", (), {"choices": [Choice()]})()


class DummyMaxTokensUnsupported:
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


def test_generate_uses_max_tokens(monkeypatch):
    monkeypatch.setattr(oc, "OpenAI", DummyOK)
    client = oc.LLM(api_key="x", chat_model="gpt")
    resp = client.generate("hi", max_tokens=42)
    assert resp == "ok"
    assert client.client.last_params["max_tokens"] == 42


def test_generate_fallback_to_max_completion_tokens(monkeypatch):
    monkeypatch.setattr(oc, "OpenAI", DummyMaxTokensUnsupported)
    client = oc.LLM(api_key="x", chat_model="gpt")
    resp = client.generate("hi", max_tokens=77)
    assert resp == "ok"
    calls = client.client.calls
    assert calls[0]["max_tokens"] == 77
    assert calls[1]["max_completion_tokens"] == 77


def test_generate_temperature_fallback(monkeypatch):
    monkeypatch.setattr(oc, "OpenAI", DummyTempUnsupported)
    client = oc.LLM(api_key="x", chat_model="gpt")
    resp = client.generate("hi", temperature=0.2)
    assert resp == "ok"
    calls = client.client.calls
    assert calls[0]["temperature"] == 0.2
    assert "temperature" not in calls[1]