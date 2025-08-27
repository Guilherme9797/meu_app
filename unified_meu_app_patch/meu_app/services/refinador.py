class RefinadorResposta:
    def __init__(self, openai_client):
        self.client = openai_client

    def refinar(self, resposta_bruta: str) -> str:
        prompt = f"""
Você é um redator jurídico para clientes leigos.
Reescreva o texto a seguir de forma clara, objetiva e organizada (use parágrafos curtos e, se fizer sentido, bullets).
Mantenha eventuais seções de "Fontes" ao final, sem alterações nos links.

TEXTO ORIGINAL:
{resposta_bruta}
"""
        return self.client.completar(prompt)
