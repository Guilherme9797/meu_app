# -*- coding: utf-8 -*-
"""Módulos de composição de respostas jurídicas."""
from typing import Any, Dict, List


class LegalComposer:
    """Compositor jurídico simplificado usado nos testes."""

    def __init__(self, llm: Any = None, logger: Any = None):
        self.llm = llm
        self.logger = logger

    def compose(self, mensagem: str, frame: Dict[str, Any], pack: List[Dict[str, Any]], coverage: float) -> str:
        """Gera uma resposta jurídica básica.

        Esta implementação é propositalmente simples; nos ambientes reais, ela
        faria uso do LLM e das referências em ``pack`` para montar a resposta.
        """
        return "Resposta jurídica não disponível neste ambiente de testes."