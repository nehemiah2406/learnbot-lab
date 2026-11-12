"""Index for uploaded files: pieces + page texts (cached as JSON) and embeddings (ChromaDB).

Everything is cached by the file's SHA-256 hash, so an unchanged file is not read or
embedded again. Works for any supported file; a part of a non-PDF file plays the role of a
page (learnbot.readers). Storage is local (config.STORAGE_DIR, gitignored).
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from learnbot import config
from learnbot import ocr
from learnbot.chunking import chunk_pages
from learnbot.readers import PDF, Part, detect_type, part_chunks, read_file

EMBED_BATCH = 256
# Vectors stored before fingerprints existed are kept if the current pieces embed to (almost)
# the same vectors: cosine at least this for every piece, and the same number of pieces.
SAME_VECTOR = 0.999


def pieces_fingerprint(document):
    """A short hash of the document's piece texts, in order: it changes when any piece changes."""
    digest = hashlib.sha256()
    for chunk in document.chunks:
        digest.update(chunk.search_text.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:32]
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
    labels: dict = field(default_factory=dict)  # {part number: location}, empty for a PDF
    ocr_pages: list = field(default_factory=list)  # PDF pages read by OCR (scanned)


def load_document(path, storage_dir=None):
    """Pieces and page texts of one file; read from the cache if the file is unchanged."""
    path = Path(path)
    digest = file_hash(path)
    cache = Path(storage_dir or config.STORAGE_DIR) / "pieces" / f"{digest}-v{config.PIECES_VERSION}.json"
    if path.suffix.lower() != ".pdf" and detect_type(path) != PDF:
        return load_parts(path, digest, cache)
    if cache.is_file():
        data = json.loads(cache.read_text(encoding="utf-8"))
        pages = {int(n): text for n, text in data["pages"].items()}
        ocr_pages = data.get("ocr_pages", [])
    else:
        pages, ocr_pages = ocr.read_pdf_pages(path)  # OCR only for scanned pages, once per file
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"pages": pages, "ocr_pages": ocr_pages}, ensure_ascii=False), encoding="utf-8")
    # Pieces are rebuilt from the cached pages (fast) and use the current file name.
    chunks = chunk_pages(path.name, pages)
    for chunk in chunks:
        if chunk.page in ocr_pages:
            chunk.where = ocr.where(chunk.page)  # the user sees the text came from OCR
    return Document(path.name, digest, pages, chunks, ocr_pages=ocr_pages)


def load_parts(path, digest, cache):
    """load_document for a non-PDF file. Raises readers.ReadError."""
    if cache.is_file():
        parts = [Part(**part) for part in json.loads(cache.read_text(encoding="utf-8"))["parts"]]
    else:
        parts = read_file(path)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"parts": [vars(part) for part in parts]}, ensure_ascii=False), encoding="utf-8")
    pages = {number: part.text for number, part in enumerate(parts, start=1)}
    labels = {number: part.label for number, part in enumerate(parts, start=1)}
    return Document(path.name, digest, pages, part_chunks(path.name, parts), labels)


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
    """ChromaDB collection per embedding model and vectors version (3-63 safe characters).
    Not per pieces version: a file whose pieces changed is embedded again by itself."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", model_name).strip("-")[-48:]
    return f"pieces-v{config.VECTORS_VERSION}-{slug}"


class VectorStore:
    """Piece embeddings in ChromaDB. Piece id = '<file hash>:<piece number>'. Every piece also
    stores its file's pieces fingerprint, so a file whose pieces changed (a new reading) is
    embedded again, and only that file: the vectors of unchanged files are never touched."""

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
        """Embed and store the document's pieces, unless they are stored already. True if
        (re)embedded. Stored pieces with another fingerprint are replaced; stored pieces with no
        fingerprint (stored before fingerprints) are kept and stamped if they still match."""
        if not document.chunks:
            return False
        fingerprint = pieces_fingerprint(document)
        stored = self.collection.get(where={"file_hash": document.file_hash}, limit=1, include=["metadatas"])
        if stored["ids"]:
            known = stored["metadatas"][0].get("pieces_hash")
            if known == fingerprint:
                return False
            if known is None and self.stamp_if_same(document, fingerprint):
                return False
            self.collection.delete(where={"file_hash": document.file_hash})
        texts = [c.search_text for c in document.chunks]
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start:start + EMBED_BATCH]
            self.collection.add(
                ids=[f"{document.file_hash}:{start + i}" for i in range(len(batch))],
                embeddings=self.embedder.encode_documents(batch),
                metadatas=[self.metadata(document, start + i, fingerprint) for i in range(len(batch))],
            )
        return True

    @staticmethod
    def metadata(document, number, fingerprint):
        return {"file_hash": document.file_hash, "piece": number, "pieces_hash": fingerprint}

    def stamp_if_same(self, document, fingerprint):
        """Old vectors (no fingerprint): True, and the fingerprint is added to their metadata
        (the vectors stay as they are), if the current pieces embed to the same vectors."""
        stored = self.collection.get(where={"file_hash": document.file_hash}, include=["embeddings", "metadatas"])
        if len(stored["ids"]) != len(document.chunks):
            return False
        old = {m["piece"]: list(v) for m, v in zip(stored["metadatas"], stored["embeddings"])}
        if set(old) != set(range(len(document.chunks))):
            return False
        texts = [c.search_text for c in document.chunks]
        for start in range(0, len(texts), EMBED_BATCH):
            fresh = self.embedder.encode_documents(texts[start:start + EMBED_BATCH])
            for i, vector in enumerate(fresh):
                if sum(a * b for a, b in zip(vector, old[start + i])) < SAME_VECTOR:
                    return False
        for start in range(0, len(texts), EMBED_BATCH):
            numbers = range(start, min(start + EMBED_BATCH, len(texts)))
            self.collection.update(ids=[f"{document.file_hash}:{n}" for n in numbers],
                                   metadatas=[self.metadata(document, n, fingerprint) for n in numbers])
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

    def only(self, name):
        """The same library with one document (same stored vectors). Raises ValueError."""
        documents = [d for d in self.documents if d.name == name]
        if not documents:
            raise ValueError(f"document not loaded: {name}")
        return Library(documents, self.store)

    def chunk(self, digest, number):
        return self._by_key.get((digest, number))

    def page_text(self, doc, page):
        """Full text of one page (None if the doc or page does not exist)."""
        return self._pages.get(doc, {}).get(page)

    def vector_search(self, text, n):
        hits = self.store.query(text, [d.file_hash for d in self.documents], n) if self.store else []
        return [c for c in (self.chunk(h, i) for h, i in hits) if c is not None]
