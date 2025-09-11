from __future__ import annotations
import json
from pathlib import Path
def _load_taxonomy_previdenciario() -> dict:
    data_path = Path(__file__).resolve().parents[2] / 'data' / 'taxonomias' / 'previdenciario.json'
    with data_path.open('r', encoding='utf-8') as f:
        return json.load(f)
_PREVID_ONTOLOGY = _load_taxonomy_previdenciario()