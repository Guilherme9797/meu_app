class RefinadorResposta:
    def __init__(self, openai_client):
        self.client = openai_client

    def refinar(self, resposta_bruta: str) -> str:
        system = "Você é um redator jurídico para clientes leigos."
        user = (
            "Reescreva o texto a seguir de forma clara, objetiva e organizada (use parágrafos curtos e, se fizer sentido, bullets).\n"
            "Mantenha eventuais seções de \"Fontes\" ao final, sem alterações nos links.\n\n"
            "TEXTO ORIGINAL:\n"
            f"{resposta_bruta}"
        )
        return self.client.chat(system=system, user=user)
