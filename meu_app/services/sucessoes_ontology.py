"""Ontologia de Direito das Sucessões para detecção temática."""


def _load_taxonomy_sucessoes() -> dict:
    return {
        "direito_das_sucessoes": {
            "inventario": {},
            "herdeiros_legitima": {},
            "testamento": {},
            "planejamento": {},
            "litigios": {},
            "internacional": {},
            "checklists": {},
        }
    }

_SUCESSOES_ONTOLOGY = _load_taxonomy_sucessoes()
