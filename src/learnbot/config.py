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
