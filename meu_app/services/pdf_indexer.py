from __future__ import annotations
from __future__ import annotations
import os, json, time, datetime as dt
from typing import List, Dict, Any, Optional
from pathlib import Path

import fitz  # PyMuPDF
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

class PDFIndexer:
    def __init__(self, *, pasta_pdfs: str = "data/pdfs", pasta_index: str = "index/faiss_index", openai_key: Optional[str] = None):
        self.pasta_pdfs = str(pasta_pdfs)
        self.pasta_index = str(pasta_index)
        os.makedirs(self.pasta_index, exist_ok=True)
        self.manifest_path = os.path.join(self.pasta_index, "manifest.json")

        # modelo de embeddings (padrão: text-embedding-3-small)
        model = os.getenv("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small")
        self.embeddings = OpenAIEmbeddings(model=model, api_key=openai_key)

        self.vs: Optional[FAISS] = None

    # ------------------------------ util ------------------------------
    def _iter_pdfs(self) -> List[str]:
        files: List[str] = []
        for root, _, fnames in os.walk(self.pasta_pdfs):
            for fn in fnames:
                if fn.lower().endswith(".pdf"):
                    files.append(os.path.join(root, fn))
        return sorted(files)

    def _load_pdf_texts(self, path: str) -> List[Document]:
        docs: List[Document] = []
        try:
            doc = fitz.open(path)
        except Exception:
            return docs

        # chunks menores => menos tokens por requisição
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=int(os.getenv("INDEX_CHUNK_SIZE", "900")),
            chunk_overlap=int(os.getenv("INDEX_CHUNK_OVERLAP", "150")),
            separators=["\n\n", "\n", ". ", " "],
        )
        for i in range(len(doc)):
            try:
                page = doc.load_page(i)
                text = (page.get_text("text") or "").strip()
                if len(text) < 80:
                    continue
                metas = {"source": str(Path(path).as_posix()), "page": i + 1}
                for part in splitter.split_text(text):
                    if part and len(part) >= 40:
                        docs.append(Document(page_content=part, metadata=metas))
            except Exception:

import argparse
import json
import os
import re
import sys
import uuid
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple

import numpy as np
from pypdf import PdfReader
from openai import OpenAI

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

RE_PROC = re.compile(r"\b\d{7}\-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")

THEMES = {
    "familia": [
        r"\bdiv[oó]rcio\b", r"\bguarda\b", r"\bvisita[s]?\b", r"\bpens[aã]o\b", r"\balimentos\b",
        r"\buni[aã]o estável\b", r"\bregime de bens\b", r"\bpartilha\b",
    ],
    "sucessoes": [
        r"\binvent[aá]rio\b", r"\bheran[çc]a\b", r"\btestamento\b", r"\barrolamento\b", r"\bsobrepartilha\b",
    ],
    "contratos": [
        r"\bcontrato\b", r"\bcl[aá]usula\b", r"\brescis[aã]o\b", r"\bmulta\b", r"\binadimpl[eê]ncia\b",
        r"\bcompra e venda\b", r"\bloc[aã]o\b", r"\bprestac[aã]o de servi[cç]os\b",
    ],
    "imobiliario": [
        r"\bposse\b", r"\busucapi[aã]o\b", r"\bdespejo\b", r"\bcondom[ií]nio\b", r"\biptu\b", r"\baluguel\b",
        r"\b[dv]is[aã]o de terra\b", r"\bregistro de im[oó]vel\b",
    ],
    "empresarial": [
        r"\bsociedade\b", r"\bcontrato social\b", r"\bquotas?\b", r"\bmarca\b", r"\bnome empresarial\b",
    ],
    "tributario": [
        r"\btribut[oos]?\b", r"\bimposto[s]?\b", r"\bicms\b", r"\biss\b", r"\birpf?\b", r"\b[pi]is\b", r"\bcofins\b",
    ],
    "consumidor": [
        r"\bprodut[o|a] defeituoso\b", r"\bgarantia\b", r"\bprocon\b", r"\bnegativ[aã]o\b", r"\bcobran[çc]a indevida\b",
        r"\bservi[cç]o\b", r"\bcdc\b",
    ],
    "processual": [
        r"\bpenhora\b", r"\bbloqueio\b", r"\bexecu[cç][aã]o\b", r"\bembargos?\b", r"\bhabeas corpus\b",
        r"\btutela de urg[eê]ncia\b", r"\bagravo\b", r"\bapela[cç][aã]o\b",
    ],
    "criminal": [
        r"\btr[aá]fico\b", r"\bporte de arma\b", r"\bfurto\b", r"\broubo\b", r"\bestelionato\b", r"\blavagem de dinheiro\b",
    ],
}
THEMES_COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in THEMES.items()}

def guess_tema(text: str) -> str:
    t = text.lower()
    best, score = "geral", 0
    for tema, pats in THEMES_COMPILED.items():
        hits = sum(1 for p in pats if p.search(t))
        if hits > score:
            best, score = tema, hits
    return best

def extract_processos(text: str) -> List[str]:
    return list({m.group(0) for m in RE_PROC.finditer(text)})

def chunk_text(pages: List[str], chunk_chars: int = 1200, overlap: int = 150) -> List[Tuple[str, str]]:
    chunks: List[Tuple[str, str]] = []
    current: List[Tuple[int, str]] = []
    for i, page_text in enumerate(pages, start=1):
        current.append((i, page_text))
    buf = ""
    span_start = current[0][0] if current else 1

    def flush_chunk(start_pg: int, end_pg: int, text: str):
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
    model: str = "text-embedding-3-small"

    def __post_init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY não definido no ambiente.")
        self.client = OpenAI(api_key=api_key)

    def embed(self, texts: List[str]) -> np.ndarray:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        vecs = [d.embedding for d in resp.data]
        arr = np.asarray(vecs, dtype="float32")
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-10
        arr = arr / norms
        return arr

def read_pdf_text(path: str) -> List[str]:
    reader = PdfReader(path)
    pages = []
    for p in reader.pages:
        try:
           pages.append(p.extract_text() or "")
        except Exception:
            pages.append("")
    return pages

def build_index(src_dir: str, out_dir: str, model: str = "text-embedding-3-small", chunk_chars: int = 1200, overlap: int = 150) -> None:
    if faiss is None:
        raise RuntimeError("FAISS não está instalado. `pip install faiss-cpu` (ou faiss-gpu).")
    os.makedirs(out_dir, exist_ok=True)
    idx_path = os.path.join(out_dir, "index.faiss")
    man_path = os.path.join(out_dir, "manifest.json")
    meta_path = os.path.join(out_dir, "meta.json")
    embedder = Embedder(model=model)
    vectors: List[np.ndarray] = []
    manifest: List[Dict[str, Any]] = []
    pdf_paths = []
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
            manifest.append({
                "chunk_id": total_chunks,
                "doc_id": doc_id,
                "doc_title": title,
                "span": span,
                "path": os.path.relpath(pdf_path),
                "tema": tema,
                "processos": processos,
                "text": text,
            })
            vectors.append(vec.reshape(1, -1))
            total_chunks += 1
        logger.info("PDF %d/%d: %s → %d chunks", pdf_idx, len(pdf_paths), fname, len(chs))
    if not vectors:
        logger.warning("Nenhum chunk gerado. Abortando escrita do índice.")
        return
    mat = np.vstack(vectors).astype("float32")
    dim = mat.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(mat)
    faiss.write_index(index, idx_path)
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"model": model, "chunks": len(manifest), "built_at": __import__("datetime").datetime.utcnow().isoformat() + "Z"}, f, ensure_ascii=False, indent=2)
    logger.info("Index salvo em: %s", idx_path)
    logger.info("Manifest salvo em: %s (%d itens)", man_path, len(manifest))

def status(out_dir: str) -> None:
    idx_path = os.path.join(out_dir, "index.faiss")
    man_path = os.path.join(out_dir, "manifest.json")
    meta_path = os.path.join(out_dir, "meta.json")
    ok_idx = os.path.exists(idx_path)
    ok_man = os.path.exists(man_path)
    print(f"index.faiss : {'OK' if ok_idx else 'MISSING'}")
    print(f"manifest.json: {'OK' if ok_man else 'MISSING'}")
    if ok_man:
        with open(man_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        print(f"Chunks: {len(manifest)}")
        if manifest:
            sample = manifest[0]
            keys = ", ".join(sorted(sample.keys()))
            print(f"Campos no manifest: {keys}")
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        print(f"Meta: {meta}")

def main(argv: List[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    p = argparse.ArgumentParser(prog="pdf_indexer", description="Constrói índice FAISS a partir de PDFs.")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="(re)constrói o índice")
    b.add_argument("--src", default=os.getenv("PDF_SRC_DIR", "data/pdfs"), help="Diretório com PDFs")
    b.add_argument("--out", default=os.getenv("RAG_INDEX_PATH", "index/faiss_index"), help="Diretório do índice FAISS")
    b.add_argument("--model", default=os.getenv("EMBED_MODEL", "text-embedding-3-small"), help="Modelo de embedding OpenAI")
    b.add_argument("--chunk", type=int, default=int(os.getenv("CHUNK_CHARS", "1200")), help="Tamanho do chunk em caracteres")
    b.add_argument("--overlap", type=int, default=int(os.getenv("CHUNK_OVERLAP", "150")), help="Sobreposição entre chunks")
    s = sub.add_parser("status", help="mostra status do índice")
    s.add_argument("--out", default=os.getenv("RAG_INDEX_PATH", "index/faiss_index"))
    args = p.parse_args(argv)
    if args.cmd == "build":
        build_index(src_dir=args.src, out_dir=args.out, model=args.model, chunk_chars=args.chunk, overlap=args.overlap)
        return 0
    elif args.cmd == "status":
        status(out_dir=args.out)
        return 0
    return 1

if __name__ == "__main__":
    raise SystemExit(main())