from meu_app.services.analisador import AnalisadorDeProblemas


class DummyClient:
    def __init__(self):
        self.calls = []

    def chat(self, system: str, user: str):
        self.calls.append((system, user))
        return "resultado"


def test_identificar_problema_builds_prompt_and_calls_chat():
    historico = [
        {"autor": "cliente", "mensagem": "Tenho um problema"},
        {"autor": "bot", "mensagem": "Como posso ajudar?"},
    ]
    client = DummyClient()
    analisador = AnalisadorDeProblemas(client)

    resp = analisador.identificar_problema(historico)

    assert resp == "resultado"
    assert len(client.calls) == 1
    system, user = client.calls[0]
    assert system.startswith("Você é um assistente jurídico")
    assert "cliente: Tenho um problema" in user