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
MAIN_LLM_TIMEOUT_S = 5  # main AI (flash-lite answered in 1-5 s in the eval)
FALLBACK_LLM_TIMEOUT_S = 15  # fallback AI(s), but never more than the time left (below)
# One question (search + all AIs + proof check) must answer in under 10 s: the AIs share
# what is left of this budget after the search. A fallback with less than
# MIN_AI_TIME_S left is skipped (the user gets "AI busy" instead of a long wait).
QUESTION_TIME_BUDGET_S = 9
MIN_AI_TIME_S = 1
# After this many failures in a row (timeout, 503, 504, ...) an AI is skipped, so users
# do not wait for the timeout on every question.
MAX_FAILURES_IN_A_ROW = 2
# A switched-off AI (not a daily limit) is tried again once every this many questions;
# if it answers, it is used again.
RETRY_SWITCHED_OFF_EVERY = 5
PROMPT_VERSION = 5  # raise when the prompt changes, so cached answers are not reused
# A quote must have at least this many words (a 2-word quote proves nothing).
MIN_QUOTE_WORDS = 4
# A paraphrased question that shares no word with the quote passes the topic check only if
# the re-ranker (RERANK_MODEL) scores (question, quote) at least this. Chosen on the eval
# set by scripts/choose_topic_threshold.py: above every trap and wrong-item quote.
# None = off: on 2 Nov 2026 no safe threshold existed (paraphrased right quotes scored
# -11 to -8, bad quotes up to 8; see eval/results.md).
TOPIC_MIN_SCORE = None
# Ask before an eval run that needs more AI calls than this.
MAX_LLM_CALLS_WITHOUT_ASKING = 50

# --- Day 1: quiz + flashcards ---------------------------------------------------------
STUDY_MIN_KEPT = 3  # a feature must keep at least this many of its 5 test items
STUDY_TRIES_PER_ITEM = 2  # pieces tried per wanted item, so dropped items can be replaced
QUIZ_TRIES_PER_QUESTION = 2  # a dropped question is tried once more, from other pieces, within its time budget
QUIZ_SEARCH_PIECES = 20  # pieces searched for those other pieces
QUIZ_SET_TRIES_PER_QUESTION = 3  # pieces tried per wanted question in a whole quiz
STUDY_MIN_PIECE_WORDS = 25  # a shorter piece is not used for a quiz with no topic

# --- Day 2: upload self-test, notebook, reading mode ----------------------------------
UPLOAD_DIR = "data/uploads"  # uploaded files (gitignored)
TEST_DOCS_DIR = "data/raw"  # the public test documents (gitignored)
SELF_TEST_QUESTIONS = 5
SELF_TEST_MIN_PASS = 3  # below this the user sees a warning but can still use the file

# --- Research mode (web search; never used for document answers) ----------------------
TAVILY_URL = "https://api.tavily.com/search"
TAVILY_TIMEOUT_S = 3  # the AI gets what is left of QUESTION_TIME_BUDGET_S
RESEARCH_RESULTS = 5  # web results sent to the AI
RESEARCH_DAILY_LIMIT = 50  # web searches per day, counted on this laptop
