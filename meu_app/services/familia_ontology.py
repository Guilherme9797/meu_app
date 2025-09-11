"""Ontologia de Direito de Família para detecção temática."""


def _load_taxonomy_familia() -> dict:
    return {
        "direito_de_familia": {
            "divorcio_partilha": {},
            "uniao_estavel": {},
            "alimentos": {},
            "guarda_visitas": {},
            "alienacao_parental": {},
            "filiacao": {},
            "medidas_protetivas": {},
            "tutela_curatela": {},
            "checklists": {},
        }
    }

_FAMILIA_ONTOLOGY = _load_taxonomy_familia()
