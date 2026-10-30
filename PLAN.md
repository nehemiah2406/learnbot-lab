# LearnBot Lab - Project Plan

AI tutor for maritime crew training. The user uploads their own PDFs; LearnBot explains and quizzes only from them, and shows weak topics. It must work on any readable PDF, not one fixed book.
Built from scratch by Hari P (Data Science Intern). Idea inspired by [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) (Apache 2.0); all code here is our own.

Status: Phase 2 (Eval set) done, Phase 3 (Baseline) next · Started 30 Oct 2026 · Target: ~5 working days

> **Main product rule:** For ANY uploaded file, LearnBot gives only exact answers from that file's text: exact numbers and units, with page and source quote, checked before showing. If not found or unsure: 'Not in this document'. Never guess.

---

## 0. Problem framing

| | |
|---|---|
| **User** | Ship crew, cadets and freshers studying a maritime topic |
| **Problem** | Long rule books are hard to read alone, there is no one to ask doubts, and it is hard to know what you have really learned |
| **Solution** | Upload any PDF (it is self-checked first), then (a) ask doubts and get an explanation with the exact source, (b) take quizzes made from the document, (c) see weak topics and practise them again |
| **Not in v1** | Login, video, voice, company documents, own backend API |

### Success metrics (must pass before "done")

| Metric | Target |
|---|---|
| Explain: answer comes from the right rule/page | 9 of 10 test questions or better |
| Quiz: correct answer is supported by the source text | 100% (wrong answer keys = 0) |
| Trap questions (not in the document) | Says "Not in this document" every time |
| Answer time | Under 10 s |
| Automated tests | All pass before every push |

---

## 1. Data

LearnBot is upload-based: users bring their own PDFs. The 3 files below are only for testing, chosen for different layouts so nothing is book-specific. All are US government works (public domain). PDFs are not committed; download them into `data/raw/` with the names below. Answers in the eval are for these exact editions.

| File (`data/raw/`) | Document | Edition / date | Official URL | Downloaded | Layout |
|---|---|---|---|---|---|
| `nav_rules.pdf` | USCG Navigation Rules and Regulations Handbook | corrected Aug 2024; 202 pages, 7.2 MB | https://www.navcen.uscg.gov/navigation-rules-amalgamated | 30 Oct 2026 | Rule book; International / Inland on facing pages; Annex I-V; two-column CFR pages 156-166 |
| `boaters_guide.pdf` | USCG "A Boater's Guide to the Federal Requirements for Recreational Boats" | revised Nov 2023; 49 pages, 2.4 MB | https://www.uscgboating.org/assets/1/AssetManager/Boaters-Guide-to-Federal-Requirements-for-Receational-Boats-20231108.pdf | 30 Oct 2026 | Booklet; title headings without numbers; few tables |
| `coast_pilot4_ch1.pdf` | NOAA U.S. Coast Pilot 4, Chapter 1 "General Information" | 25 OCT 2026 edition (updated weekly; answers are for this edition); 36 pages, 1.2 MB | https://nauticalcharts.noaa.gov/publications/coast-pilot/files/cp4/CPB4_C01_WEB.pdf | 30 Oct 2026 | Two columns, numbered paragraphs (1), (2) ...; tables |

- **Upload self-check (part of v1):** `src/learnbot/pdf_check.py` runs on every upload: size (max 50 MB), opens / password, pages (max 1000), text per page, low-text (scanned?) pages, tables, sample text, general heading finder (Rule / Section / Chapter / Article / Part / Annex / Appendix / 1.2) with numbering gaps, verdict OK / WARNING / FAIL plus info notes. Limits and thresholds in `src/learnbot/config.py`
- **Column-aware reading:** `src/learnbot/pdf_text.py` `read_page_text()` finds column gutters from word positions and reads each column top to bottom; table-like columns (short cells) stay row by row. Everything that reads page text (self-check, eval checker, app) uses it
- **Self-check results** (`reports/data_check_<file>.md`): all 3 files OK. nav_rules: Rule 1-38 and Annex I-V found, no gaps, 12 blank divider pages, contents on pages 4-5. boaters_guide: no numbered headings (note), 3 near-empty pages. coast_pilot4_ch1: no numbered headings (note), 30 of 36 pages two-column
- **Cleaning rules for Phase 4:** cover page text of nav_rules is tripled by bold print (`IISSBBNN`; pdfplumber `dedupe_chars()` fixes it); International and Inland versions of the same rule sit on facing pages (headers `—INTERNATIONAL—` / `—INLAND—`) and must be kept apart; Coast Pilot paragraph numbers `(1)`, `(2)` sit on their own line

---

## 2. Architecture (v1)

```
PDF upload -> self-check (OK / WARNING / FAIL) -> read pages (pdfplumber) -> clean -> split by rule/section -> embeddings (local, sentence-transformers)
    -> vector store (ChromaDB, local) -> search top 3-5 pieces
    -> LLM writes answer / quiz (Gemini main, Groq fallback) -> checks -> Streamlit app
progress (scores per topic) -> local file/SQLite
```

- **LLM:** Gemini (main) + Groq (fallback when Gemini is busy or out of quota). Own keys in `.env` only.
- **No own backend API in v1.** Streamlit runs UI + logic. FastAPI can be added later if another app must call LearnBot.
- **Token saving:** send only the top 3-5 pieces, cache generated quizzes, reuse answers to repeated questions, embeddings run locally.

---

## 3. Phases

| # | Phase | Output | Done when |
|---|---|---|---|
| 0 | Problem framing | This plan | Hari agrees |
| 1 | Data + upload self-check | `src/learnbot/pdf_check.py`, `scripts/data_check.py`, reports | Self-check works on any PDF; we know layout, issues, cleaning rules |
| 2 | Eval set first | `eval/explain_questions.csv`, `eval/quiz_rules.md`, trap questions | 20+ questions with expected rule/page |
| 3 | Baseline | Keyword search answer | Baseline score recorded |
| 4 | RAG pipeline | Read, chunk, embed, store, search, answer with source; Gemini + Groq fallback; timeouts | Beats baseline, meets explain target |
| 5 | Quiz generation + upload self-test | MCQ from document + validation (answer must be in source, rules in `eval/quiz_rules.md`). **Upload self-test:** when any new file is uploaded, LearnBot makes 5 questions with quotes from that file and checks that it answers them exactly from the right page | 0 wrong answer keys on eval; self-test passes on all 3 test PDFs |
| 6 | Progress | Scores per topic, weak-topic re-quiz | Works across app restarts |
| 7 | Evaluate + improve | `eval/results.md` table | All success metrics pass |
| 8 | App | Streamlit UI, friendly errors; runs the upload self-check and the upload self-test on every new file. **If the self-test fails, the user sees a warning** | Demo works end to end |
| 9 | Ship | Tests, README, GitHub, resume line | Pushed + verified on GitHub |

---

## 4. Quality rules (from day 1)

0. **Main product rule:** For ANY uploaded file, LearnBot gives only exact answers from that file's text: exact numbers and units, with page and source quote, checked before showing. If not found or unsure: 'Not in this document'. Never guess.
1. Eval set first, with expected answers. Wrong answers must be 0.
2. General rules only, never one-off fixes for one question.
3. When unsure, say "Not in this document" instead of guessing. Never invent numbers.
4. Timeout + friendly fallback on every external call (Gemini, Groq).
5. Self-check when a new document is uploaded.
6. Thumbs-down answers are saved into the eval list.
7. Run tests + eval before every push; one commit per change.

---

## 5. Progress log

| Date | What was done |
|---|---|
| 30 Oct 2026 | Plan written, data source chosen (COLREGs handbook, 202 pages), LLM plan Gemini + Groq |
| 30 Oct 2026 | Phase 1 done: scope changed to upload-based (any PDF). Built reusable upload self-check `pdf_check.py` + `scripts/data_check.py` (file or folder), 37 tests pass. nav_rules.pdf verdict OK, cleaning rules noted |
| 30 Oct 2026 | Phase 2 prep: added boaters_guide.pdf and coast_pilot4_ch1.pdf (official URLs, editions recorded); column-aware reading (`pdf_text.py`); "no numbered headings" is now an info note; all 3 PDFs self-check OK; 46 tests pass |
| 30 Oct 2026 | Phase 2 done: eval set over 3 documents. `eval/explain_questions.csv` 29 questions (nav_rules 13, boaters_guide 8, coast_pilot4_ch1 8; fact 9, number 9, compare 3, paraphrase 6, annex 2), `eval/trap_questions.csv` 8 traps (3/3/2), `eval/quiz_rules.md`. Checker `src/learnbot/eval_check.py` + `scripts/check_eval.py`: 29/29 quotes verified on their page, 8/8 trap keywords absent. Main product rule added first in CLAUDE.md and PLAN.md; upload self-test planned in Phase 5 and 8. 138 tests pass |
