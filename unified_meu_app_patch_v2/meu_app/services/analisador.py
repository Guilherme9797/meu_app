from __future__ import annotations

class AnalisadorDeProblemas:
    def __init__(self, openai_client):
        self.client = openai_client

    # novo: usado por server.py para extrair um resumo a partir de uma pergunta solta
    def analisar(self, pergunta: str) -> dict:
        system = "Você resume problemas jurídicos em 1-2 frases (PT-BR), e sugere uma área em [area: ...]."
        user = f"Pergunta do cliente:\n{pergunta}\n\nResuma em 1-2 frases. Ao final, inclua [area: ...]."
        texto = self.client.chat(system=system, user=user)
        resumo = (texto or "").strip()
        return {"resumo": resumo, "raw": texto}

    # legado: mantém compatibilidade com callers antigos
    def identificar_problema(self, historico):
        contexto = "\n".join([f"{msg['autor']}: {msg['mensagem']}" for msg in historico])
        system = "Você identifica o problema jurídico e etiqueta a área no formato [area: ...]."
        user = f"Histórico:\n{contexto}\n\nResponda com 1 frase + [area: ...]."
        return self.client.chat(system=system, user=user)
