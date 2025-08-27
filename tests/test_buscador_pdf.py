from meu_app.services import buscador_pdf
from meu_app.services.buscador_pdf import BuscadorPDF


class DummyIndexer:
    def __init__(self, *args, **kwargs):
        self.index_called = False

    def load_index(self):
        return True

    def indexar_pdfs(self):
        self.index_called = True
        return {"ok": True}

    def atualizar_indice_verbose(self):
        return {"verbose": True}

    def buscar_resposta(self, pergunta, k=6, max_distance=0.35):
        return "resposta do pdf"

    def buscar_contexto(self, consulta, k=5):
        return ""


def test_atualizar_indice_chama_indexar(monkeypatch):
    monkeypatch.setattr(buscador_pdf, "PDFIndexer", DummyIndexer)
    b = BuscadorPDF(openai_key="test")

    result = b.atualizar_indice()

    assert result == {"ok": True}
    assert b.indexador.index_called is True