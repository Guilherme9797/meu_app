from __future__ import annotations

"""Orquestrador do fluxo de atendimento baseado em múltiplos módulos."""

from typing import Any, Dict

from .legal_frame import frame_case
from .concepts import ConceptBank
from .rag import search_all
from .generator import generate_answer
from .guardrails import refine_if_needed

# Importa todas as taxonomias disponíveis para expansão semântica
from .administrativo_ontology import _ADMINISTRATIVO_ONTOLOGY
from .ambiental_ontology import _AMBIENTAL_ONTOLOGY
from .consumidor_ontology import _CONSUMIDOR_ONTOLOGY
from .empresarial_ontology import _EMPRESARIAL_ONTOLOGY
from .imobiliario_ontology import _IMOBILIARIO_ONTOLOGY
from .penal_ontology import _PENAL_ONTOLOGY
from .previdenciario_ontology import _PREVID_ONTOLOGY
from .proc_penal_ontology import _PROC_PENAL_ONTOLOGY
from .proc_trab_ontology import _PROC_TRAB_ONTOLOGY
from .trabalho_ontology import _TRABALHO_ONTOLOGY
from .tributario_ontology import _TRIBUTARIO_ONTOLOGY
from .familia_ontology import _FAMILIA_ONTOLOGY
from .sucessoes_ontology import _SUCESSOES_ONTOLOGY

TAXONOMIAS = [
    _ADMINISTRATIVO_ONTOLOGY,
    _AMBIENTAL_ONTOLOGY,
    _CONSUMIDOR_ONTOLOGY,
    _EMPRESARIAL_ONTOLOGY,
    _IMOBILIARIO_ONTOLOGY,
    _PENAL_ONTOLOGY,
    _PREVID_ONTOLOGY,
    _PROC_PENAL_ONTOLOGY,
    _PROC_TRAB_ONTOLOGY,
    _TRABALHO_ONTOLOGY,
    _TRIBUTARIO_ONTOLOGY,
    _FAMILIA_ONTOLOGY,
    _SUCESSOES_ONTOLOGY,
]

def atender(llm: Any, pergunta: str) -> Dict[str, Any]:
    """Pipeline completo de atendimento jurídico."""
    frame = frame_case(llm, pergunta)
    qterms = ConceptBank(TAXONOMIAS).expand(frame)
    pack = search_all(qterms, frame)
    answer = generate_answer(llm, pergunta, frame, pack)
    answer = refine_if_needed(llm, pergunta, frame, pack, answer)
    return answer