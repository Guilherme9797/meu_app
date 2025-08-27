from meu_app.services.refinador import RefinadorResposta


class DummyClient:
    def __init__(self):
        self.calls = []

    def chat(self, system: str, user: str):
        self.calls.append((system, user))
        return "refinada"


def test_refinar_usa_chat_com_prompt_apropriado():
    client = DummyClient()
    refinador = RefinadorResposta(client)

    texto = "Texto original"
    resp = refinador.refinar(texto)

    assert resp == "refinada"
    assert len(client.calls) == 1
    system, user = client.calls[0]
    assert system.startswith("Você é um redator jurídico")
    assert "TEXTO ORIGINAL" in user
    assert texto in user