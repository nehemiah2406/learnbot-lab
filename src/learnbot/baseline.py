"""Baseline keyword search (BM25) over chunks from all uploaded PDFs. No AI.

Why BM25 and not plain TF-IDF: a word repeated many times in a piece counts less
and less (saturation), and long pieces are not favoured just for being long
(length normalisation). It is the standard keyword baseline in search research.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

from learnbot import config

NOT_FOUND = "Not in this document"
K1 = 1.5  # how fast repeated words stop adding score
B = 0.75  # how much long pieces are penalised
TOP_K = 3

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "by", "for", "from",
    "with", "as", "is", "are", "be", "been", "was", "were", "it", "its", "this", "that",
    "these", "those", "what", "which", "who", "whom", "when", "where", "why", "how",
    "do", "does", "did", "i", "my", "me", "we", "you", "your", "he", "she", "her",
    "his", "they", "their", "them", "if", "than", "then", "there", "so", "not", "no",
    "can", "may", "must", "shall", "should", "will", "would", "has", "have", "had",
    "any", "all", "each", "every", "under", "about", "into", "up", "out", "other",
}
TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[a-z]+")
SAME_CHARS = str.maketrans({"’": "'", "–": "-", "—": "-", "−": "-"})


def tokenize(text):
    """Lowercase words and numbers ("2,000" -> "2000"), common words removed."""
    tokens = TOKEN.findall(text.lower().translate(SAME_CHARS))
    return [t.replace(",", "") for t in tokens if t not in STOPWORDS]


@dataclass
class Hit:
    score: float
    chunk: object


class BM25Index:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.term_counts = [Counter(tokenize(c.search_text)) for c in self.chunks]
        self.lengths = [sum(tc.values()) for tc in self.term_counts]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0
        doc_freq = Counter(term for tc in self.term_counts for term in tc)
        n = len(self.chunks)
        self.idf = {t: math.log(1 + (n - df + 0.5) / (df + 0.5)) for t, df in doc_freq.items()}

    def score(self, query_terms, i):
        tc, length = self.term_counts[i], self.lengths[i]
        total = 0.0
        for term in query_terms:
            tf = tc.get(term, 0)
            if tf:
                norm = K1 * (1 - B + B * length / self.avg_length)
                total += self.idf[term] * tf * (K1 + 1) / (tf + norm)
        return total

    def search(self, query, k=TOP_K):
        """Top k hits, best first. Words not in any piece are ignored."""
        terms = set(tokenize(query)) & self.idf.keys()
        if not terms:
            return []
        scored = [(self.score(terms, i), i) for i in range(len(self.chunks))]
        scored.sort(key=lambda s: (-s[0], s[1]))
        return [Hit(score, self.chunks[i]) for score, i in scored[:k] if score > 0]


def answer(index, question, min_score=None):
    """(NOT_FOUND or None, top hits). None means: the top hit is the answer."""
    min_score = config.BASELINE_MIN_SCORE if min_score is None else min_score
    hits = index.search(question)
    if not hits or hits[0].score < min_score:
        return NOT_FOUND, hits
    return None, hits
