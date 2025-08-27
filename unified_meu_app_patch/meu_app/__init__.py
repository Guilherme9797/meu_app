# meu_app/__init__.py — pacote raiz
from .models import Cliente, HistoricoConversa, HistoricoConversaPersistente
# Submódulos expostos para conveniência
from . import models, persistence, services

__all__ = [
    "Cliente",
    "HistoricoConversa",
    "HistoricoConversaPersistente",
    "models",
    "persistence",
    "services",
]
