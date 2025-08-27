from __future__ import annotations
import os
import json
import time
import logging
from typing import List, Dict, Any, Optional, Tuple

# Dependências
import fitz  # PyMuPDF
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

log = logging.getLogger("pdf_indexer")
log.setLevel(os.getenv("LOGLEVEL", "INFO"))

def _env_int(name: str, default: int) -> int:
    try:
        v = int(str(os.getenv(name, default)).strip())
        return max(0, v)
    except Exception:
        return default

def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, default)).strip())
    except Exception:
        return default

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _list_pdfs(pdf_dir: str) -> List[str]:
    if not os.path.isdir(pdf_dir):
        return []
    out = []
    for name in os.listdir(pdf_dir):
        if name.lower().endswith(".pdf"):
            out.append(os.path.join(pdf_dir, name))
    out.sort()
    return out

def _read_pdf_pages(path: str, max_pages: Optional[int]) -> List[Tuple[int, str]]:
    texts: List[Tuple[int, str]] = []
    with fitz.open(path) as doc:
        total = len(doc)
        stop = total if not max_pages or max_pages <= 0 else min(total, max_pages)
        for i in range(stop):
            pg = doc.load_page(i)
            txt = pg.get_text("text") or ""
            txt = txt.replace("\x00", "").strip()
            texts.append((i + 1, txt))
    return texts

def _chunk_text(txt: str, fast: bool) -> List[str]:
    # chunking simples por tamanho; em "fast", chunks maiores e menos overlap
    max_chars = 1400 if fast else 1000
    overlap = 80 if fast else 150

    txt = " ".join(txt.split())  # compacta espaços
    if not txt:
        return []

    chunks: List[str] = []
    start = 0
    while start < len(txt):
        end = min(len(txt), start + max_chars)
        chunk = txt[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(txt):
            break
        start = max(end - overlap, start + 1)
    return chunks

class PDFIndexer:
    """
    Indexador de PDFs em FAISS com embeddings da OpenAI, com APIs para busca.
    Construtor aceita tanto (pasta_pdfs, pasta_index) quanto (pdf_dir, index_dir).
    """

    def __init__(
        self,
        pasta_pdfs: Optional[str] = None,
        pasta_index: Optional[str] = None,
        openai_key: Optional[str] = None,
        *,
        pdf_dir: Optional[str] = None,
        index_dir: Optional[str] = None,
    ) -> None:
        # aliases compat
        self.pdf_dir = pdf_dir or pasta_pdfs or os.getenv("PDFS_DIR", "data/pdfs")
        self.index_dir = index_dir or pasta_index or os.getenv("INDEX_DIR", "index/faiss_index")

        # dotenv fallback
        try:
            from dotenv import load_dotenv, find_dotenv
            load_dotenv(find_dotenv(usecwd=True), override=False)
        except Exception:
            pass

        key = (openai_key or os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY não definido — configure no .env ou passe openai_key")

        # Parâmetros de embeddings
        self.embed_model = os.getenv("EMBED_MODEL", "text-embedding-3-small")
        self.embed_timeout = _env_float("EMBED_TIMEOUT", 40.0)
        self.embed_retries = _env_int("EMBED_RETRIES", 2)
        self.embed_batch = max(1, _env_int("EMBED_BATCH", 16))

        # Cria o objeto de embeddings com timeout/retries
        self.embeddings = OpenAIEmbeddings(
            api_key=key,
            model=self.embed_model,
            timeout=self.embed_timeout,
            max_retries=self.embed_retries,
        )

        # Limites (modo rápido)
        self.fast_mode = os.getenv("INDEX_FAST", "").strip() not in ("", "0", "false", "False")
        self.max_pages = _env_int("PDF_MAX_PAGES", 0)  # 0 = sem limite
        self.max_docs = _env_int("INDEX_MAX_DOCS", 0)
        self.max_chunks = _env_int("INDEX_MAX_CHUNKS", 0)

        _ensure_dir(self.index_dir)
        self.index: Optional[FAISS] = None

    # -------------------- Carregar / (Re)indexar --------------------

    def load_index(self) -> bool:
        """Tenta carregar o índice salvo em disco. Retorna True se ok."""
        try:
            self.index = FAISS.load_local(
                self.index_dir,
                self.embeddings,
                allow_dangerous_deserialization=True,
            )
            return True
        except Exception as e:
            log.info("PDFIndexer: não foi possível carregar índice: %s", e)
            self.index = None
            return False

    def indexar_pdfs(self) -> Dict[str, Any]:
        """(Re)constrói o índice do zero com batching e logs de progresso."""
        pdfs = _list_pdfs(self.pdf_dir)
        if self.max_docs > 0:
            pdfs = pdfs[: self.max_docs]

        all_texts: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        t0 = time.time()
        for path in pdfs:
            fname = os.path.basename(path)
            try:
                pages = _read_pdf_pages(path, self.max_pages if self.max_pages > 0 else None)
                if not pages:
                    continue

                for (page_no, txt) in pages:
                    if self.fast_mode and not txt.strip():
                        continue
                    for chunk in _chunk_text(txt, self.fast_mode):
                        all_texts.append(chunk)
                        metadatas.append({"source": fname, "page": page_no})
                        if self.max_chunks and len(all_texts) >= self.max_chunks:
                            break
                    if self.max_chunks and len(all_texts) >= self.max_chunks:
                        break
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log.warning("Falha lendo %s: %s", fname, e)

        if not all_texts:
            # ainda salva um manifest vazio
            self._write_manifest([], 0)
            return {
                "indexed_files": 0,
                "chunks": 0,
                "index_dir": self.index_dir,
                "manifest": os.path.join(self.index_dir, "manifest.json"),
            }

        # -------------------- Embedding em lotes --------------------
        vectors: List[List[float]] = []
        total = len(all_texts)
        batch = self.embed_batch
        log.info("Gerando embeddings (%d chunks em lotes de %d) – modelo=%s timeout=%.1fs",
                total, batch, self.embed_model, self.embed_timeout)

        try:
            for i in range(0, total, batch):
                sub = all_texts[i : i + batch]
                vecs = self.embeddings.embed_documents(sub)
                vectors.extend(vecs)
        except KeyboardInterrupt:
            log.warning("Interrompido pelo usuário durante embeddings.")
            raise

        if len(vectors) != len(all_texts):
            raise RuntimeError(f"Número de vetores ({len(vectors)}) != textos ({len(all_texts)})")

        # -------------------- Monta FAISS e salva --------------------
        text_embeddings = list(zip(all_texts, vectors))
        store = FAISS.from_embeddings(text_embeddings=text_embeddings, embedding=self.embeddings, metadatas=metadatas)
        store.save_local(self.index_dir)
        self.index = store  # mantém em memória

        dt = time.time() - t0
        self._write_manifest(pdfs, len(all_texts))

        return {
            "indexed_files": len(pdfs),
            "chunks": len(all_texts),
            "index_dir": self.index_dir,
            "manifest": os.path.join(self.index_dir, "manifest.json"),
            "elapsed_sec": round(dt, 2),
            "fast_mode": self.fast_mode,
            "batch": self.embed_batch,
        }

    # método compatível com chamadas antigas
    def atualizar_indice_verbose(self) -> Dict[str, Any]:
        return self.indexar_pdfs()

    # -------------------- Busca --------------------

    def _ensure_loaded(self) -> bool:
        if self.index is not None:
            return True
        return self.load_index()

    def search(self, pergunta: str, k: int = 6) -> List[Tuple[str, Dict[str, Any], float]]:
        """Retorna lista de (texto, metadata, score). Quanto menor o score, mais similar."""
        if not self._ensure_loaded():
            return []
        try:
            # similarity_search_with_score: maior score = melhor, mas a API de LC depende da versão.
            # Vamos usar similarity_search_with_score e inverter para um pseudo-dist.
            docs_scores = self.index.similarity_search_with_score(pergunta, k=k)
            out = []
            for d, score in docs_scores:
                md = d.metadata or {}
                out.append((d.page_content, md, float(score)))
            return out
        except Exception as e:
            log.warning("Falha na busca FAISS: %s", e)
            return []

    def buscar_resposta(self, pergunta: str, k: int = 6, max_distance: float = 0.35) -> str:
        """Concatena trechos mais relevantes, com indicação de fonte."""
        results = self.search(pergunta, k=k)
        if not results:
            return ""
        partes = []
        for texto, md, score in results:
            # score aqui é arbitrário; apenas filtramos os piores com limite frouxo
            if score is not None and score > 1e8:
                # algumas versões retornam distâncias muito grandes; ignore
                continue
            fonte = f"{md.get('source','?')} p.{md.get('page','?')}"
            partes.append(f"{texto}\n(Fonte: {fonte})")
        return "\n\n".join(partes[:k])

    def buscar_contexto(self, pergunta: str, k: int = 5) -> str:
        """Retorna apenas os trechos brutos para servir de contexto a LLMs."""
        results = self.search(pergunta, k=k)
        if not results:
            return ""
        return "\n\n".join([txt for (txt, _md, _s) in results[:k]])

    # -------------------- util --------------------

    def _write_manifest(self, files: List[str], chunks: int) -> None:
        manifest = {
            "files": [os.path.basename(f) for f in files],
            "count": chunks,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": self.embed_model,
            "batch": self.embed_batch,
            "fast_mode": self.fast_mode,
            "max_pages": self.max_pages,
        }
        with open(os.path.join(self.index_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
