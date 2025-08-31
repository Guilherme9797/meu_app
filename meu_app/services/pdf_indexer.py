from __future__ import annotations

"""Ferramentas para indexar PDFs em um índice FAISS."""

import argparse
import json
import os
import re
import sys
import uuid
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional

import numpy as np
try:  # pragma: no cover - pode não estar instalado
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover
    PdfReader = None  # type: ignore
from openai import OpenAI

try:  # pragma: no cover - faiss pode não estar instalado em todos os ambientes
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None  # type: ignore

logger = logging.getLogger(__name__)

RE_PROC = re.compile(r"\b\d{7}\-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")


# ---------------------------------------------------------------------------
# Utilidades de processamento de texto
# ---------------------------------------------------------------------------

THEMES = {
    "familia": [
        r"\bdiv[oó]rcio\b",
        r"\bguarda\b",
        r"\bvisita[s]?\b",
        r"\bpens[aã]o\b",
        r"\balimentos\b",
        r"\buni[aã]o estável\b",
        r"\bregime de bens\b",
        r"\bpartilha\b",
    ],
    "sucessoes": [
        r"\binvent[aá]rio\b",
        r"\bheran[çc]a\b",
        r"\btestamento\b",
        r"\barrolamento\b",
        r"\bsobrepartilha\b",
    ],
    "contratos": [
        r"\bcontrato\b",
        r"\bcl[aá]usula\b",
        r"\brescis[aã]o\b",
        r"\bmulta\b",
        r"\binadimpl[eê]ncia\b",
        r"\bcompra e venda\b",
        r"\bloc[aã]o\b",
        r"\bprestac[aã]o de servi[cç]os\b",
    ],
    "imobiliario": [
        r"\bposse\b",
        r"\busucapi[aã]o\b",
        r"\bdespejo\b",
        r"\bcondom[ií]nio\b",
        r"\biptu\b",
        r"\baluguel\b",
        r"\b[dv]is[aã]o de terra\b",
        r"\bregistro de im[oó]vel\b",
    ],
    "empresarial": [
        r"\bsociedade\b",
        r"\bcontrato social\b",
        r"\bquotas?\b",
        r"\bmarca\b",
        r"\bnome empresarial\b",
    ],
    "tributario": [
        r"\btribut[oos]?\b",
        r"\bimposto[s]?\b",
        r"\bicms\b",
        r"\biss\b",
        r"\birpf?\b",
        r"\b[pi]is\b",
        r"\bcofins\b",
    ],
    "consumidor": [
        r"\bprodut[o|a] defeituoso\b",
        r"\bgarantia\b",
        r"\bprocon\b",
        r"\bnegativ[aã]o\b",
        r"\bcobran[çc]a indevida\b",
        r"\bservi[cç]o\b",
        r"\bcdc\b",
    ],
    "processual": [
        r"\bpenhora\b",
        r"\bbloqueio\b",
        r"\bexecu[cç][aã]o\b",
        r"\bembargos?\b",
        r"\bhabeas corpus\b",
        r"\btutela de urg[eê]ncia\b",
        r"\bagravo\b",
        r"\bapela[cç][aã]o\b",
    ],
    "criminal": [
        r"\btr[aá]fico\b",
        r"\bporte de arma\b",
        r"\bfurto\b",
        r"\broubo\b",
        r"\bestelionato\b",
        r"\blavagem de dinheiro\b",
    ],
}
THEMES_COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in THEMES.items()}


def guess_tema(text: str) -> str:
    """Heurística simples para inferir o tema do texto."""
    t = text.lower()
    best, score = "geral", 0
    for tema, pats in THEMES_COMPILED.items():
        hits = sum(1 for p in pats if p.search(t))
        if hits > score:
            best, score = tema, hits
    return best


def extract_processos(text: str) -> List[str]:
    return list({m.group(0) for m in RE_PROC.finditer(text)})


def chunk_text(pages: List[str], *, chunk_chars: int = 1200, overlap: int = 150) -> List[Tuple[str, str]]:
    """Quebra um documento em chunks preservando as páginas de origem."""
    chunks: List[Tuple[str, str]] = []
    current: List[Tuple[int, str]] = []
    for i, page_text in enumerate(pages, start=1):
        current.append((i, page_text))
    buf = ""
    span_start = current[0][0] if current else 1

    def flush_chunk(start_pg: int, end_pg: int, text: str) -> None:
        span = f"p. {start_pg}" if start_pg == end_pg else f"p. {start_pg}-{end_pg}"
        chunks.append((span, text.strip()))

    pg_cursor = span_start
    for (pg, txt) in current:
        units = txt.split("\n")
        for line in units:
            if not line.strip():
                continue
            candidate = (buf + ("\n" if buf else "") + line).strip()
            if len(candidate) >= chunk_chars:
                cut = candidate.rfind(" ", 0, chunk_chars)
                if cut < 0:
                    cut = chunk_chars
                part = candidate[:cut].strip()
                flush_chunk(span_start, pg_cursor, part)
                start_overlap = max(0, cut - overlap)
                buf = candidate[start_overlap:].strip()
                span_start = pg_cursor
            else:
                buf = candidate
            pg_cursor = pg
    if buf:
        flush_chunk(span_start, pg_cursor, buf)
    return chunks


@dataclass
class Embedder:
    """Wrapper simples para a API de embeddings da OpenAI."""

    model: str = "text-embedding-3-small"
    api_key: Optional[str] = None

    def __post_init__(self) -> None:  # pragma: no cover - validação trivial
        key = self.api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY não definido no ambiente.")
        self.client = OpenAI(api_key=key)

    def embed(self, texts: List[str]) -> np.ndarray:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        vecs = [d.embedding for d in resp.data]
        arr = np.asarray(vecs, dtype="float32")
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-10
        arr = arr / norms
        return arr


def read_pdf_text(path: str) -> List[str]:
    if PdfReader is None:
        raise RuntimeError("pypdf não está instalado.")
    reader = PdfReader(path)
    pages: List[str] = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:  # pragma: no cover - defensivo
            pages.append("")
    return pages


def build_index(
    src_dir: str,
    out_dir: str,
    *,
    model: str = "text-embedding-3-small",
    chunk_chars: int = 1200,
    overlap: int = 150,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Varre `src_dir`, gera embeddings e grava índice + manifest."""

    if faiss is None:
        raise RuntimeError(
            "FAISS não está instalado. `pip install faiss-cpu` (ou faiss-gpu)."
        )
    os.makedirs(out_dir, exist_ok=True)
    idx_path = os.path.join(out_dir, "index.faiss")
    man_path = os.path.join(out_dir, "manifest.json")
    meta_path = os.path.join(out_dir, "meta.json")
    embedder = Embedder(model=model, api_key=api_key)
    vectors: List[np.ndarray] = []
    manifest: List[Dict[str, Any]] = []
    pdf_paths: List[str] = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdf_paths.append(os.path.join(root, f))
    pdf_paths.sort()
    logger.info("Encontrados %d PDFs em %s", len(pdf_paths), src_dir)
    total_chunks = 0
    for pdf_idx, pdf_path in enumerate(pdf_paths, start=1):
        try:
            pages = read_pdf_text(pdf_path)
        except Exception:
            logger.exception("Falha ao ler PDF: %s", pdf_path)
            continue

        fname = os.path.basename(pdf_path)
        title = os.path.splitext(fname)[0]
        doc_id = f"{title}_{uuid.uuid4().hex[:8]}"

        chs = chunk_text(pages, chunk_chars=chunk_chars, overlap=overlap)
        if not chs:
            continue

        texts = [c[1] for c in chs]
        vecs = embedder.embed(texts)
        for (span, text), vec in zip(chs, vecs):
            tema = guess_tema(text)
            processos = extract_processos(text)
            manifest.append(
                {
                    "chunk_id": total_chunks,
                    "doc_id": doc_id,
                    "doc_title": title,
                    "span": span,
                    "path": os.path.relpath(pdf_path),
                    "tema": tema,
                    "processos": processos,
                    "text": text,
                }
            )
            vectors.append(vec.reshape(1, -1))
            total_chunks += 1

        logger.info(
            "PDF %d/%d: %s → %d chunks",
            pdf_idx,
            len(pdf_paths),
            fname,
            len(chs),
        )
    if not vectors:
        logger.warning("Nenhum chunk gerado. Abortando escrita do índice.")
        return {"pdfs": 0, "chunks": 0, "index_dir": out_dir, "manifest": man_path}

    mat = np.vstack(vectors).astype("float32")
    dim = mat.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(mat)
    faiss.write_index(index, idx_path)

    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model": model,
                "chunks": len(manifest),
                "built_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    logger.info("Index salvo em: %s", idx_path)
    logger.info("Manifest salvo em: %s (%d itens)", man_path, len(manifest))
    return {
        "pdfs": len(pdf_paths),
        "chunks": len(manifest),
        "index_dir": out_dir,
        "manifest": man_path,
    }

def _status(out_dir: str) -> None:
    idx_path = os.path.join(out_dir, "index.faiss")
    man_path = os.path.join(out_dir, "manifest.json")
    meta_path = os.path.join(out_dir, "meta.json")

    print(f"index.faiss : {'OK' if os.path.exists(idx_path) else 'MISSING'}")
    print(f"manifest.json: {'OK' if os.path.exists(man_path) else 'MISSING'}")
    if os.path.exists(man_path):
        try:
            with open(man_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            count = len(manifest) if isinstance(manifest, list) else manifest.get("count", 0)
            print(f"Chunks: {count}")
        except Exception:  # pragma: no cover - leitura defensiva
            pass
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            print(f"Meta: {meta}")
        except Exception:  # pragma: no cover
            pass


# ---------------------------------------------------------------------------
# Classe de alto nível usada pelo CLI principal
# ---------------------------------------------------------------------------


class PDFIndexer:
    """Wrapper orientado a objeto para construção do índice."""

    def __init__(
        self,
        *,
        pasta_pdfs: str = "data/pdfs",
        pasta_index: str = "index/faiss_index",
        openai_key: Optional[str] = None,
    ) -> None:
        self.pasta_pdfs = pasta_pdfs
        self.pasta_index = pasta_index
        self.openai_key = openai_key

    # A implementação atual não faz atualização incremental; apenas rebuild
    def indexar_pdfs(self) -> Dict[str, Any]:
        return build_index(
            self.pasta_pdfs,
            self.pasta_index,
            model=os.getenv("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small"),
            chunk_chars=int(os.getenv("INDEX_CHUNK_SIZE", "1200")),
            overlap=int(os.getenv("INDEX_CHUNK_OVERLAP", "150")),
            api_key=self.openai_key,
        )

    def atualizar_indice_verbose(self) -> Dict[str, Any]:
        # Para simplificar, delega ao rebuild completo
        return self.indexar_pdfs()


# ---------------------------------------------------------------------------
# CLI do módulo
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        argv = ["status"]
    p = argparse.ArgumentParser(prog="pdf_indexer", description="Constrói índice FAISS a partir de PDFs")
    sub = p.add_subparsers(dest="cmd")

    b = sub.add_parser("build", help="(re)constrói o índice")
    b.add_argument("--src", default=os.getenv("PDF_SRC_DIR", "data/pdfs"), help="Diretório com PDFs")
    b.add_argument(
        "--out",
        default=os.getenv("RAG_INDEX_PATH", "index/faiss_index"),
        help="Diretório do índice FAISS",
    )
    b.add_argument(
        "--model",
        default=os.getenv("EMBED_MODEL", "text-embedding-3-small"),
        help="Modelo de embedding OpenAI",
    )
    b.add_argument(
        "--chunk",
        type=int,
        default=int(os.getenv("CHUNK_CHARS", "1200")),
        help="Tamanho do chunk em caracteres",
    )
    b.add_argument(
        "--overlap",
        type=int,
        default=int(os.getenv("CHUNK_OVERLAP", "150")),
        help="Sobreposição entre chunks",
    )

    s = sub.add_parser("status", help="Mostra status do índice")
    s.add_argument(
        "--out", default=os.getenv("RAG_INDEX_PATH", "index/faiss_index"), help="Diretório do índice"
    )

    args = p.parse_args(argv)

    if args.cmd == "build":
        build_index(
            src_dir=args.src,
            out_dir=args.out,
            model=args.model,
            chunk_chars=args.chunk,
            overlap=args.overlap,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        return 0
    if args.cmd == "status":
        _status(args.out)
        return 0

    p.print_help()
    return 1
if __name__ == "__main__":  # pragma: no cover - execução via CLI
    raise SystemExit(main())
            