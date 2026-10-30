# LearnBot Lab - Project Plan

AI tutor for maritime crew training. Upload a training document, ask doubts, take quizzes, see weak topics.
Built from scratch by Hari P (Data Science Intern). Idea inspired by [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) (Apache 2.0); all code here is our own.

Status: Phase 1 (Data) in progress · Started 30 Oct 2026 · Target: ~5 working days

---

## 0. Problem framing

| | |
|---|---|
| **User** | Ship crew, cadets and freshers studying a maritime topic |
| **Problem** | Long rule books are hard to read alone, there is no one to ask doubts, and it is hard to know what you have really learned |
| **Solution** | Upload a PDF, then (a) ask doubts and get an explanation with the exact source, (b) take quizzes made from the document, (c) see weak topics and practise them again |
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

- **Document:** USCG Navigation Rules and Regulations Handbook (COLREGs), corrected Aug 2024, 202 pages
- **Source:** https://www.navcen.uscg.gov/navigation-rules-amalgamated (US Coast Guard NAVCEN, US government work)
- **Stored at:** `data/raw/nav_rules.pdf` (not committed; README explains how to download)
- **Data check (EDA) to do:** text vs scanned pages, characters per page, page layout (columns, International vs Inland text), rule numbering, tables/annexes, headers/footers to clean

---

## 2. Architecture (v1)

```
PDF -> read pages (pdfplumber) -> clean -> split by rule/section -> embeddings (local, sentence-transformers)
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
| 1 | Data | `notebooks/01_data_check` or `scripts/data_check.py` + notes | We know layout, issues, cleaning rules |
| 2 | Eval set first | `eval/explain_questions.csv`, `eval/quiz_rules.md`, trap questions | 20+ questions with expected rule/page |
| 3 | Baseline | Keyword search answer | Baseline score recorded |
| 4 | RAG pipeline | Read, chunk, embed, store, search, answer with source; Gemini + Groq fallback; timeouts | Beats baseline, meets explain target |
| 5 | Quiz generation | MCQ from document + validation (answer must be in source) | 0 wrong answer keys on eval |
| 6 | Progress | Scores per topic, weak-topic re-quiz | Works across app restarts |
| 7 | Evaluate + improve | `eval/results.md` table | All success metrics pass |
| 8 | App | Streamlit UI, friendly errors | Demo works end to end |
| 9 | Ship | Tests, README, GitHub, resume line | Pushed + verified on GitHub |

---

## 4. Quality rules (from day 1)

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
