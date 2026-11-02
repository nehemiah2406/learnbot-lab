"""Index for uploaded PDFs: pieces + page texts (cached as JSON) and embeddings (ChromaDB).

Everything is cached by the file's SHA-256 hash, so an unchanged file is not read or
embedded again. Works for any PDF; storage is local (config.STORAGE_DIR, gitignored).
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from learnbot import config
from learnbot.chunking import chunk_pages, read_pdf_pages

EMBED_BATCH = 256
# Some models want a short instruction before the question (not before the pieces).
QUERY_PREFIX = {
    "BAAI/bge-small-en-v1.5": "Represent this sentence for searching relevant passages: ",
}


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class Document:
    name: str
    file_hash: str
    pages: dict  # {page number: text}
    chunks: list


def load_document(path, storage_dir=None):
    """Pieces and page texts of one PDF; read from the cache if the file is unchanged."""
    path = Path(path)
    digest = file_hash(path)
    cache = Path(storage_dir or config.STORAGE_DIR) / "pieces" / f"{digest}-v{config.PIECES_VERSION}.json"
    if cache.is_file():
        data = json.loads(cache.read_text(encoding="utf-8"))
        pages = {int(n): text for n, text in data["pages"].items()}
    else:
        pages = read_pdf_pages(path)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"pages": pages}, ensure_ascii=False), encoding="utf-8")
    # Pieces are rebuilt from the cached pages (fast) and use the current file name.
    return Document(path.name, digest, pages, chunk_pages(path.name, pages))


# --- Embeddings ---------------------------------------------------------------------
class Embedder:
    """Local sentence-transformers model, loaded on first use."""

    def __init__(self, model_name=None):
        self.name = model_name or config.EMBED_MODEL
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.name, device="cpu")
        return self._model

    def encode_documents(self, texts):
        vectors = self._load().encode(list(texts), batch_size=64, normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    def encode_query(self, text):
        return self.encode_documents([QUERY_PREFIX.get(self.name, "") + text])[0]


def collection_name(model_name):
    """ChromaDB collection per embedding model and pieces version (3-63 safe characters)."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", model_name).strip("-")[-48:]
    return f"pieces-v{config.PIECES_VERSION}-{slug}"


class VectorStore:
    """Piece embeddings in ChromaDB. Piece id = '<file hash>:<piece number>'."""

    def __init__(self, embedder, storage_dir=None):
        import chromadb
        from chromadb.config import Settings

        self.embedder = embedder
        path = Path(storage_dir or config.STORAGE_DIR) / "chroma"
        client = chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
        self.collection = client.get_or_create_collection(
            collection_name(embedder.name),
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
        )

    def has(self, digest):
        return bool(self.collection.get(where={"file_hash": digest}, limit=1)["ids"])

    def add(self, document):
        """Embed and store the document's pieces, unless this file is already stored."""
        if self.has(document.file_hash) or not document.chunks:
            return False
        texts = [c.search_text for c in document.chunks]
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start:start + EMBED_BATCH]
            self.collection.add(
                ids=[f"{document.file_hash}:{start + i}" for i in range(len(batch))],
                embeddings=self.embedder.encode_documents(batch),
                metadatas=[{"file_hash": document.file_hash, "piece": start + i} for i in range(len(batch))],
            )
        return True

    def query(self, text, digests, n):
        """[(file hash, piece number)] best first, only from the given files."""
        if not digests:
            return []
        where = {"file_hash": {"$in": list(digests)}}
        result = self.collection.query(query_embeddings=[self.embedder.encode_query(text)],
                                       n_results=n, where=where, include=["metadatas"])
        return [(m["file_hash"], m["piece"]) for m in result["metadatas"][0]]


class Library:
    """All uploaded documents: pieces, page texts and (optionally) their vectors."""

    def __init__(self, documents, store=None):
        self.documents = list(documents)
        self.store = store
        self.chunks = [c for d in self.documents for c in d.chunks]
        self._by_key = {(d.file_hash, i): c for d in self.documents for i, c in enumerate(d.chunks)}
        self._pages = {d.name: d.pages for d in self.documents}

    @classmethod
    def load(cls, paths, store=None, storage_dir=None):
        documents = [load_document(p, storage_dir) for p in paths]
        if store is not None:
            for d in documents:
                store.add(d)
        return cls(documents, store)

    def chunk(self, digest, number):
        return self._by_key.get((digest, number))

    def page_text(self, doc, page):
        """Full text of one page (None if the doc or page does not exist)."""
        return self._pages.get(doc, {}).get(page)

    def vector_search(self, text, n):
        hits = self.store.query(text, [d.file_hash for d in self.documents], n) if self.store else []
        return [c for c in (self.chunk(h, i) for h, i in hits) if c is not None]
