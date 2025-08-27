class AnalisadorDeProblemas:
    def __init__(self, openai_client):
        self.client = openai_client

    def identificar_problema(self, historico):
        contexto = "\n".join([f"{msg['autor']}: {msg['mensagem']}" for msg in historico])
        prompt = f"""
Abaixo está o histórico de conversas com um cliente.
Identifique qual é o problema jurídico e a área envolvida (ex: família, consumidor, cível, penal).
Responda com UMA frase que descreva o problema e UMA etiqueta de área ao final, no formato: [área: ...].
Histórico:
{contexto}
"""
        return self.client.completar(prompt)
