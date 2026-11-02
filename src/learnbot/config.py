"""Settings for LearnBot. Change values here, not inside the code."""

# Upload limits
MAX_FILE_MB = 50
MAX_PAGES = 1000

# A page with fewer characters than this may be blank or scanned.
LOW_TEXT_CHARS = 100

# Share of low-text pages that gives a WARNING / FAIL verdict.
LOW_TEXT_WARN_RATIO = 0.10
LOW_TEXT_FAIL_RATIO = 0.50

# This many broken-text marks (replacement char or "(cid:N)") gives a WARNING.
MESSY_TEXT_WARN_COUNT = 10

# Characters shown as a sample of the extracted text.
SAMPLE_CHARS = 300

# Baseline keyword search (Phase 3): best BM25 score below this -> "Not in this document".
# Chosen from the threshold sweep in eval/results.md.
BASELINE_MIN_SCORE = 11.5

# --- Phase 4: search + AI answers ---------------------------------------------------
STORAGE_DIR = "storage"  # pieces + ChromaDB vectors, cached by file hash (gitignored)
CACHE_DIR = "cache"  # saved AI answers (gitignored)
PIECES_VERSION = 1  # raise when chunking changes, so cached pieces are rebuilt

# Local embedding model (sentence-transformers). Chosen by eval, see eval/results.md.
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
# Optional local re-ranker (cross-encoder); None = off. Chosen by eval.
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
SEARCH_METHOD = "hybrid"  # "bm25", "embed" or "hybrid" (reciprocal rank fusion)
RRF_K = 60  # standard reciprocal rank fusion constant
SEARCH_CANDIDATES = 50  # pieces taken from each search before fusing
PIECES_TO_LLM = 5  # only this many pieces are sent to the AI
# Rule-set words: if a question names one and a document has pages headed with each of
# them, the answer must come from a page headed with the named one.
RULE_SET_WORDS = ("International", "Inland")

# AI models (names can be changed in .env: GEMINI_MODEL, GROQ_MODEL).
# Checked with scripts/list_models.py on 2 Nov 2026. Timed with one tiny call each:
# gemini-3.1-flash-lite 1.5 s, gemini-3.5-flash 2.7 s, gemini-3.8-flash 504 after 13.6 s.
GEMINI_MODEL = "gemini-3.1-flash-lite"
GROQ_MODEL = "openai/gpt-oss-120b"  # no Llama 70B model is offered on this Groq account
LLM_TIMEOUT_S = 15
# After this many failures in a row (timeout, 503, 504) an AI is skipped for the rest
# of the run, so users do not wait LLM_TIMEOUT_S on every question.
MAX_FAILURES_IN_A_ROW = 2
PROMPT_VERSION = 1  # raise when the prompt changes, so cached answers are not reused
# A quote must have at least this many words (a 2-word quote proves nothing).
MIN_QUOTE_WORDS = 4
# Ask before an eval run that needs more AI calls than this.
MAX_LLM_CALLS_WITHOUT_ASKING = 50
