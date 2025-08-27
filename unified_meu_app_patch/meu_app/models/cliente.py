import uuid
from datetime import datetime

class Cliente:
    def __init__(self, nome: str):
        self.id = str(uuid.uuid4())
        self.nome = nome
        self.data_criacao = datetime.now()

    def __repr__(self):
        return f"<Cliente {self.nome} | ID: {self.id}>"
