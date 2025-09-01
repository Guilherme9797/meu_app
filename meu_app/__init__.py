"""Pacote principal do aplicativo."""

from .handlers import handle_incoming, is_resolution_confirmation, sess_repo

__all__ = [
    "models",
    "services",
    "persistence",
    "utils",
    "handle_incoming",
    "is_resolution_confirmation",
    "sess_repo",
]
__version__ = "0.3.0"  # Etapa 3 – Fechamento (pagamentos)