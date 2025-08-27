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