from __future__ import annotations

import os
from pathlib import Path

# Diretório raiz do repositório (dois níveis acima deste arquivo)
_REPO_ROOT = Path(__file__).resolve().parents[2]
# Caminho padrão para o índice FAISS dentro do repositório
DEFAULT_INDEX_DIR = _REPO_ROOT / "index" / "faiss_index"

def get_index_dir() -> str:
    """Retorna o diretório do índice FAISS.

    Usa a variável de ambiente INDEX_DIR, se definida, caso contrário
    aponta para ``index/faiss_index`` relativo à raiz do projeto.
    """
    return os.getenv("INDEX_DIR", str(DEFAULT_INDEX_DIR))