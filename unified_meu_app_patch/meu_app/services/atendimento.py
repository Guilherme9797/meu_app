from __future__ import annotations

from typing import Optional

# --- Suporte para rodar como módulo do pacote (-m) ou diretamente (python services/atendimento.py) ---
if __package__ is None or __package__ == "":
    # Execução direta: injeta o diretório-pai que contém "meu_app" no sys.path
    import os, sys
    _here = os.path.abspath(__file__)
    _services_dir = os.path.dirname(_here)                          # .../meu_app/services
    _pkg_root = os.path.dirname(_services_dir)                      # .../meu_app
    _project_root = os.path.dirname(_pkg_root)                      # diretório que CONTÉM "meu_app"
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    from meu_app.models.historico import HistoricoConversaPersistente
    from meu_app.persistence.repositories import ClienteRepository
else:
    # Execução normal como pacote
    from ..models.historico import HistoricoConversaPersistente
    from ..persistence.repositories import ClienteRepository


class Atendimento:
    """
    Orquestra o fluxo:
      1) registra mensagem do cliente no histórico
      2) identifica o problema (analisador)
      3) busca resposta (PDFs -> internet se necessário)
      4) refina a resposta final
      5) registra resposta no histórico
    """

    def __init__(
        self,
        cliente,
        analisador,
        buscador,
        refinador,
        historico: Optional[HistoricoConversaPersistente] = None,
    ):
        self.cliente = cliente
        self.analisador = analisador
        self.buscador = buscador
        self.refinador = refinador

        self.cliente_repo = ClienteRepository()
        # garante registro do cliente (idempotente se o repo já tratar)
        self.cliente_repo.criar(cliente.id, cliente.nome, cliente.data_criacao)

        self.historico = historico or HistoricoConversaPersistente(cliente.id)

    def receber_mensagem(self, mensagem: str) -> str:
        self.historico.registrar_mensagem("cliente", mensagem)

        problema = self.analisador.identificar_problema(self.historico.obter_historico())

        bruto = self.buscador.buscar_resposta(problema) or ""
        if not bruto.strip():
            bruto = self.buscador.buscar_na_internet(problema) or ""

        final = self.refinador.refinar(bruto)
        self.historico.registrar_mensagem("assistente", final)
        return final


if __name__ == "__main__":
    # Dica de execução
    print("[Atendimento] módulo carregado. Execute via: python -m meu_app.services.atendimento")
