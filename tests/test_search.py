"""Search, rule sets, index cache and report sections with made-up data (no models, no AI)."""

import math

from learnbot import index as index_module
from learnbot.chunking import Chunk
from learnbot.index import Document, Library, VectorStore, collection_name, load_document
from learnbot.report import replace_section
from learnbot.rule_sets import RuleSets
from learnbot import search as search_module
from learnbot.search import Searcher, default_searcher, rrf

INTL = Chunk("rules.pdf", 45, "—INTERNATIONAL— Rule 22", "(a) masthead light range 6 miles for vessels of 50 meters.")
INLAND = Chunk("rules.pdf", 46, "—INLAND— Rule 22", "(a) masthead light range 6 miles for a vessel of 50 meters.")
INLAND_LATER = Chunk("rules.pdf", 46, "Distress Signals", "(p) a white light flashing 50 to 70 times per minute.")
GUIDE = Chunk("guide.pdf", 9, "Inland waters", "Numbers must be at least 3 inches high on inland boats.")
CHUNKS = [INTL, INLAND, INLAND_LATER, GUIDE]


# --- Reciprocal rank fusion -----------------------------------------------------------
def test_rrf_rewards_pieces_ranked_high_in_both_lists():
    assert rrf([["a", "b", "c"], ["b", "c", "a"]], k=60)[0] == "b"
    assert rrf([["a"], ["c"]], k=60) == ["a", "c"]  # tie keeps first-seen order
    assert rrf([]) == []


# --- Rule sets ------------------------------------------------------------------------
def test_page_label_comes_from_any_heading_on_the_page():
    rules = RuleSets(CHUNKS)
    assert rules.label("rules.pdf", 45) == "International"
    assert rules.label("rules.pdf", 46) == "Inland"  # INLAND_LATER's own title has no rule set


def test_rule_set_question_only_answered_from_pages_of_that_set():
    rules = RuleSets(CHUNKS)
    assert rules.docs_with_sets == {"rules.pdf"}  # guide has only "Inland" in a title
    question = "Under the International Rules, how far must the masthead light be visible?"
    assert rules.allowed(question, "rules.pdf", 45) and not rules.allowed(question, "rules.pdf", 46)
    assert not rules.allowed(question, "guide.pdf", 9)  # a page without the International label
    assert rules.allowed("How far must the masthead light be visible?", "guide.pdf", 9)


def test_no_rule_set_filter_when_no_document_has_rule_sets():
    guide_only = RuleSets([c for c in CHUNKS if c.doc == "guide.pdf"])
    assert guide_only.docs_with_sets == set()
    assert guide_only.allowed("Under the International Rules, what is it?", "guide.pdf", 9)


def test_question_naming_both_or_none_has_no_rule_set():
    rules = RuleSets(CHUNKS)
    assert rules.asked("Compare the International and Inland rules") is None
    assert rules.asked("How tall must numbers be?") is None
    assert rules.asked("under the INLAND rules?") == "Inland"


# --- Searcher -------------------------------------------------------------------------
def library(store=None):
    return Library([Document("rules.pdf", "h1", {}, CHUNKS[:3]), Document("guide.pdf", "h2", {}, [GUIDE])], store)


def test_bm25_search_with_rule_set_filter():
    question = "Under the Inland Rules, what is the masthead light range for 50 meters?"
    assert Searcher(library(), "bm25").search(question, k=1)[0] is INLAND
    no_filter = Searcher(library(), "bm25", use_rule_sets=False).search(question, k=5)
    assert INTL in no_filter
    assert INTL not in Searcher(library(), "bm25").search(question, k=5)


class FakeStore:
    def __init__(self, hits):
        self.hits = hits

    def query(self, text, digests, n):
        return [h for h in self.hits if h[0] in digests][:n]


def test_hybrid_search_fuses_keyword_and_vector_results():
    # Vector search says the guide piece; keyword search finds nothing for "boat lettering".
    searcher = Searcher(library(FakeStore([("h2", 0), ("h1", 0)])), "hybrid")
    assert searcher.search("boat lettering height", k=1)[0] is GUIDE


class ReverseReranker:
    def scores(self, question, texts):
        return [-i for i in range(len(texts))][::-1]  # last candidate gets the best score


def test_reranker_reorders_candidates():
    plain = Searcher(library(FakeStore([("h1", 0), ("h1", 1), ("h2", 0)])), "embed", use_rule_sets=False)
    ranked = Searcher(plain.library, "embed", use_rule_sets=False, reranker=ReverseReranker())
    assert ranked.search("x", k=3) == plain.search("x", k=3)[::-1]


# --- Index cache ----------------------------------------------------------------------
def test_unchanged_file_is_not_read_again(tmp_path, monkeypatch):
    reads = []

    def fake_reader(path):
        reads.append(path)
        return {1: "(a) A vessel shall keep a proper look-out at all times by sight and hearing."}, []

    monkeypatch.setattr(index_module.ocr, "read_pdf_pages", fake_reader)
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"version 1")
    first = load_document(pdf, tmp_path / "storage")
    second = load_document(pdf, tmp_path / "storage")
    assert len(reads) == 1 and first.file_hash == second.file_hash and second.chunks[0].doc == "book.pdf"
    pdf.write_bytes(b"version 2")
    load_document(pdf, tmp_path / "storage")
    assert len(reads) == 2  # changed file -> read again


class FakeEmbedder:
    name = "fake/embedder"

    def __init__(self):
        self.batches = 0

    def vector(self, text):
        v = [float(sum(ord(ch) for ch in word) % 7) + 1 for word in text.split()[:8]]
        v += [0.5] * (8 - len(v))
        norm = math.sqrt(sum(x * x for x in v))
        return [x / norm for x in v]

    def encode_documents(self, texts):
        self.batches += 1
        return [self.vector(t) for t in texts]

    def encode_query(self, text):
        return self.vector(text)


def test_vector_store_embeds_each_file_once(tmp_path):
    embedder = FakeEmbedder()
    store = VectorStore(embedder, tmp_path)
    doc = Document("rules.pdf", "hash1", {}, CHUNKS[:3])
    assert store.add(doc) and not store.add(doc)
    assert embedder.batches == 1
    again = VectorStore(embedder, tmp_path)  # new session, same storage
    assert again.has("hash1") and not again.has("hash2")
    hits = again.query("masthead light", ["hash1"], 2)
    assert len(hits) == 2 and all(h[0] == "hash1" for h in hits)
    assert again.query("masthead light", ["hash2"], 2) == [] and again.query("x", [], 2) == []


def test_collection_name_is_safe():
    name = collection_name("BAAI/bge-small-en-v1.5")
    assert 3 <= len(name) <= 63 and "/" not in name


# --- Report sections ------------------------------------------------------------------
def test_replace_section_keeps_other_sections(tmp_path):
    path = tmp_path / "results.md"
    replace_section(path, "a", "## A\nold")
    replace_section(path, "b", "## B")
    replace_section(path, "a", "## A\nnew")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Results") and "new" in text and "old" not in text
    assert text.index("## A") < text.index("## B")


def test_models_load_when_the_search_starts_not_on_the_first_question(monkeypatch):
    # Real case: the first chat question of a self-test got "AI busy" on every try.
    searches = []
    monkeypatch.setattr(search_module.config, "RERANK_MODEL", None)
    monkeypatch.setattr(search_module.config, "SEARCH_METHOD", "bm25")
    monkeypatch.setattr(Searcher, "search", lambda self, question, k=None: searches.append(question) or [])
    default_searcher(Library([Document("a.pdf", "h", {1: "text"}, [Chunk("a.pdf", 1, "T", "text")])]))
    assert len(searches) == 1


# --- Vectors are kept per file: only a file whose pieces changed is embedded again ------
from learnbot import config  # noqa: E402
from learnbot.index import pieces_fingerprint  # noqa: E402


class CountingEmbedder(FakeEmbedder):
    def __init__(self):
        super().__init__()
        self.texts = 0

    def encode_documents(self, texts):
        self.texts += len(texts)
        return super().encode_documents(texts)


def stored(store, digest):
    got = store.collection.get(where={"file_hash": digest}, include=["embeddings", "metadatas"])
    return {i: (dict(m), [round(x, 6) for x in v]) for i, m, v in zip(got["ids"], got["metadatas"], got["embeddings"])}


def add_old_style(store, document, texts=None):
    """Vectors as stored before fingerprints: no pieces_hash in the metadata."""
    texts = texts or [c.search_text for c in document.chunks]
    store.collection.add(ids=[f"{document.file_hash}:{i}" for i in range(len(texts))],
                         embeddings=store.embedder.encode_documents(texts),
                         metadatas=[{"file_hash": document.file_hash, "piece": i} for i in range(len(texts))])


def test_changed_pieces_are_embedded_again_and_other_files_are_not_touched(tmp_path):
    embedder = CountingEmbedder()
    store = VectorStore(embedder, tmp_path)
    keep, change = Document("keep.pdf", "hash1", {}, CHUNKS[:2]), Document("spread.pdf", "hash2", {}, CHUNKS[2:3])
    assert store.add(keep) and store.add(change)
    before_keep = stored(store, "hash1")
    embedder.texts = 0
    new_reading = Document("spread.pdf", "hash2", {}, [CHUNKS[3], CHUNKS[2]])  # same file, new pieces
    again = VectorStore(embedder, tmp_path)
    assert not again.add(keep) and again.add(new_reading)
    assert embedder.texts == 2  # only the changed file was embedded
    assert stored(again, "hash1") == before_keep  # the other file's vectors and ids are untouched
    now = stored(again, "hash2")
    assert sorted(now) == ["hash2:0", "hash2:1"]
    assert {m["pieces_hash"] for m, _ in now.values()} == {pieces_fingerprint(new_reading)}
    assert not again.add(new_reading)  # stored now: nothing to do


def test_fewer_pieces_leave_no_old_vectors_behind(tmp_path):
    store = VectorStore(CountingEmbedder(), tmp_path)
    store.add(Document("a.pdf", "hash1", {}, CHUNKS[:3]))
    store.add(Document("a.pdf", "hash1", {}, CHUNKS[:1]))
    assert sorted(stored(store, "hash1")) == ["hash1:0"]


def test_old_vectors_that_still_match_are_kept_and_stamped(tmp_path):
    embedder = CountingEmbedder()
    store = VectorStore(embedder, tmp_path)
    doc = Document("rules.pdf", "hash1", {}, CHUNKS[:3])
    add_old_style(store, doc)
    before = stored(store, "hash1")
    assert not store.add(doc)  # same texts: the stored vectors are kept
    after = stored(store, "hash1")
    assert {i: v for i, (_, v) in after.items()} == {i: v for i, (_, v) in before.items()}
    assert {m["pieces_hash"] for m, _ in after.values()} == {pieces_fingerprint(doc)}
    embedder.texts = 0
    assert not store.add(doc) and embedder.texts == 0  # stamped: no embedding needed any more


def test_old_vectors_of_other_texts_are_replaced(tmp_path):
    store = VectorStore(CountingEmbedder(), tmp_path)
    doc = Document("rules.pdf", "hash1", {}, CHUNKS[:3])
    add_old_style(store, doc, texts=["mixed columns text one two", "mixed columns three four five", "six seven"])
    assert store.add(doc)
    assert {m["pieces_hash"] for m, _ in stored(store, "hash1").values()} == {pieces_fingerprint(doc)}


def test_old_vectors_with_another_number_of_pieces_are_replaced(tmp_path):
    store = VectorStore(CountingEmbedder(), tmp_path)
    doc = Document("rules.pdf", "hash1", {}, CHUNKS[:3])
    add_old_style(store, doc, texts=[c.search_text for c in CHUNKS[:2]])
    assert store.add(doc)
    assert sorted(stored(store, "hash1")) == ["hash1:0", "hash1:1", "hash1:2"]


def test_fingerprint_changes_with_text_and_order():
    a = Document("a.pdf", "h", {}, CHUNKS[:2])
    assert pieces_fingerprint(a) == pieces_fingerprint(Document("b.pdf", "h", {}, CHUNKS[:2]))
    assert pieces_fingerprint(a) != pieces_fingerprint(Document("a.pdf", "h", {}, [CHUNKS[1], CHUNKS[0]]))
    assert pieces_fingerprint(a) != pieces_fingerprint(Document("a.pdf", "h", {}, CHUNKS[:3]))


def test_new_pieces_version_keeps_the_vector_collection(monkeypatch):
    name = collection_name("BAAI/bge-small-en-v1.5")
    monkeypatch.setattr(config, "PIECES_VERSION", config.PIECES_VERSION + 1)
    assert collection_name("BAAI/bge-small-en-v1.5") == name
    assert name.startswith(f"pieces-v{config.VECTORS_VERSION}-")
    assert config.VECTORS_VERSION == 2  # the existing collection keeps its name, so it is reused
