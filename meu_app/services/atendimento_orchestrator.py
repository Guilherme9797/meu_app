# -*- coding: utf-8 -*-
"""Orquestrador principal do atendimento jurídico."""
from typing import Dict, Any
from os import getenv
from meu_app.nlu.interpreter import UniversalInterpreter
from meu_app.services.buscador_pdf import BuscadorPDF
from meu_app.generator.generator import LegalComposer
from meu_app.generator.client_pitch_generator import ClientPitchGenerator

USE_PITCH_ALWAYS = getenv("USE_PITCH_ALWAYS", "false").lower() in ("1", "true", "yes")

class AtendimentoOrchestrator:
    def __init__(self, llm, logger, branding: Dict[str, str] | None = None):
        self.llm = llm
        self.logger = logger
        self.nlu = UniversalInterpreter()
        self.buscador = BuscadorPDF(logger=logger)
        self.legal = LegalComposer(llm=llm, logger=logger)
        self.pitch = ClientPitchGenerator(llm=llm, logger=logger, branding=branding)

    def handle(self, mensagem: str, cliente: Dict[str, Any]) -> str:
        """Processa a mensagem do usuário e decide entre resposta legal ou pitch."""
        # Se você quiser SEMPRE usar o pitch comercial:
        if USE_PITCH_ALWAYS:
            return self.pitch.compose(mensagem, extra_context={"cliente": cliente})

        # Caso contrário, roda o pipeline normal e, se vier genérico ou com baixa cobertura, usa pitch:
        frame = self.nlu.parse(mensagem)
        pack, coverage = self.buscador.search_hybrid(frame.queries, top_k=12, bm25=True, semantic=True)

        resposta = self.legal.compose(mensagem, frame, pack, coverage)
        # Heurística: se a resposta ficou muito genérica/triagem, troca para pitch comercial
        # Considera também cobertura ausente ou abaixo de 0.55 (valor mais alto que 0.35 anterior)
        if (
            "Diagnóstico" in resposta
            and "O que fazer agora" in resposta
            and (coverage is None or coverage < 0.55)
        ):
            if self.logger:
                self.logger.info("Cobertura baixa/saída genérica — usando ClientPitchGenerator.")
            return self.pitch.compose(mensagem, extra_context={"frame": frame, "cliente": cliente})

        return resposta