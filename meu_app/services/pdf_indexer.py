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
                continue
        doc.close()
        return docs

    # ------------------------------ index ------------------------------
    def indexar_pdfs(self) -> Dict[str, Any]:
        start = time.time()
        pdfs = self._iter_pdfs()

        all_docs: List[Document] = []
        for p in pdfs:
            all_docs.extend(self._load_pdf_texts(p))

        # sempre escreve manifest (mesmo vazio) para facilitar debug
        def _write_manifest(files_list: List[str], chunks_count: int, scanned_count: int):
            manifest = {
                "files": files_list,
                "count": chunks_count,
                "scanned": scanned_count,
                "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

        if not all_docs:
            # limpa index antigo, se existir
            for fn in ("index.faiss", "index.pkl"):
                fpath = os.path.join(self.pasta_index, fn)
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
            _write_manifest([], 0, len(pdfs))
            return {"indexed_files": 0, "chunks": 0, "index_dir": self.pasta_index, "manifest": self.manifest_path}

        # ---------- construção com batching para evitar 300k tokens ----------
        batch_docs = int(os.getenv("INDEX_EMBED_BATCH_DOCS", "32"))
        batch_docs = max(4, min(batch_docs, 128))

        store: Optional[FAISS] = None
        i = 0
        while i < len(all_docs):
            batch = all_docs[i : i + batch_docs]
            try:
                if store is None:
                    store = FAISS.from_documents(batch, self.embeddings)
                else:
                    store.add_documents(batch)
                i += batch_docs
            except Exception as e:
                msg = str(e)
                # Se estourar tokens por requisição, reduzir o tamanho do lote e tentar novamente
                if "max_tokens_per_request" in msg or ("Requested" in msg and "max" in msg):
                    if batch_docs <= 4:
                        raise
                    batch_docs = max(4, batch_docs // 2)
                    continue
                raise

        if store is None:
            _write_manifest([], 0, len(pdfs))
            return {"indexed_files": 0, "chunks": 0, "index_dir": self.pasta_index, "manifest": self.manifest_path}

        self.vs = store
        self.vs.save_local(self.pasta_index)
        files_list = [str(Path(p).as_posix()) for p in pdfs]
        _write_manifest(files_list, len(all_docs), len(pdfs))
        return {"indexed_files": len(pdfs), "chunks": len(all_docs), "index_dir": self.pasta_index, "manifest": self.manifest_path}

    def atualizar_indice_verbose(self) -> Dict[str, Any]:
        return self.indexar_pdfs()

    def load_index(self) -> bool:
        try:
            self.vs = FAISS.load_local(self.pasta_index, self.embeddings, allow_dangerous_deserialization=True)
            return True
        except Exception:
            self.vs = None
            return False

    # ------------------------------ consulta ------------------------------
    def buscar_contexto(self, consulta: str, *, k: int = 5) -> str:
        if not self.vs and not self.load_index():
            return ""
        try:
            hits = self.vs.similarity_search(consulta, k=k)
        except Exception:
            return ""
        blocos = []
        for h in hits:
            src = h.metadata.get("source")
            page = h.metadata.get("page")
            blocos.append(f"[{src}#p{page}] {h.page_content}")
        return "\n\n".join(blocos)

    def buscar_resposta(self, pergunta: str, *, k: int = 6, max_distance: float = 0.4) -> str:
        return self.buscar_contexto(pergunta, k=k)
