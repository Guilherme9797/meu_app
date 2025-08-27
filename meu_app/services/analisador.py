class AnalisadorDeProblemas:
    def __init__(self, openai_client):
        self.client = openai_client

    def identificar_problema(self, historico):
        contexto = "\n".join([f"{msg['autor']}: {msg['mensagem']}" for msg in historico])
        user = (
            "Abaixo está o histórico de conversas com um cliente.\n"
            "Identifique qual é o problema jurídico e a área envolvida (ex: família, consumidor, cível, penal).\n"
            "Responda com UMA frase que descreva o problema e UMA etiqueta de área ao final, no formato: [área: ...].\n"
            "Histórico:\n"
            f"{contexto}"
        )
        system = "Você é um assistente jurídico que classifica problemas e áreas do direito."
        return self.client.chat(system=system, user=user)
