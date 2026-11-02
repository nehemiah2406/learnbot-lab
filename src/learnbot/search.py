"""Search pieces for a question: BM25 (keywords), embeddings (meaning) or both (hybrid).

Hybrid uses reciprocal rank fusion (RRF): each piece gets 1 / (RRF_K + rank) from each
list it appears in. Ranks are combined, not scores, so BM25 and cosine scores never
need to be put on the same scale. Optional: drop pieces from the wrong rule set and
re-rank the best candidates with a local cross-encoder.
"""

from learnbot import config
from learnbot.baseline import BM25Index
from learnbot.rule_sets import RuleSets

METHODS = ("bm25", "embed", "hybrid")
RERANK_CANDIDATES = 20


def rrf(rank_lists, k=None):
    """Fuse ranked lists of keys into one list, best first (ties keep first-seen order)."""
    k = config.RRF_K if k is None else k
    scores, order = {}, []
    for ranked in rank_lists:
        for rank, key in enumerate(ranked, start=1):
            if key not in scores:
                scores[key] = 0.0
                order.append(key)
            scores[key] += 1 / (k + rank)
    return sorted(order, key=lambda key: -scores[key])


class CrossEncoderReranker:
    """Local cross-encoder that scores (question, piece) pairs; loaded on first use."""

    def __init__(self, model_name):
        self.name = model_name
        self._model = None

    def scores(self, question, texts):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.name, device="cpu")
        return list(self._model.predict([(question, t) for t in texts]))


class Searcher:
    def __init__(self, library, method=None, use_rule_sets=True, reranker=None):
        self.library = library
        self.method = method or config.SEARCH_METHOD
        if self.method not in METHODS:
            raise ValueError(f"unknown search method: {self.method}")
        self.use_rule_sets = use_rule_sets
        self.reranker = reranker
        self.chunks = library.chunks
        self.position = {id(c): i for i, c in enumerate(self.chunks)}
        self.bm25 = BM25Index(self.chunks)
        self.rule_sets = RuleSets(self.chunks)

    def ranked(self, question, n):
        """Piece positions, best first, from the chosen method."""
        lists = []
        if self.method in ("bm25", "hybrid"):
            lists.append([self.position[id(h.chunk)] for h in self.bm25.search(question, k=n)])
        if self.method in ("embed", "hybrid"):
            lists.append([self.position[id(c)] for c in self.library.vector_search(question, n)])
        return rrf(lists) if len(lists) > 1 else (lists[0] if lists else [])

    def search(self, question, k=None):
        """The k pieces to send to the AI, best first."""
        k = k or config.PIECES_TO_LLM
        pieces = [self.chunks[i] for i in self.ranked(question, config.SEARCH_CANDIDATES)]
        if self.use_rule_sets:
            pieces = [c for c in pieces if self.rule_sets.allowed(question, c.doc, c.page)]
        if self.reranker is not None and pieces:
            top = pieces[:RERANK_CANDIDATES]
            scores = self.reranker.scores(question, [c.search_text for c in top])
            pieces = [c for _, c in sorted(zip(scores, top), key=lambda s: -s[0])]
        return pieces[:k]


def default_searcher(library):
    """The search chosen by eval (config.SEARCH_METHOD, rule sets on, optional re-ranker)."""
    reranker = CrossEncoderReranker(config.RERANK_MODEL) if config.RERANK_MODEL else None
    return Searcher(library, config.SEARCH_METHOD, use_rule_sets=True, reranker=reranker)
