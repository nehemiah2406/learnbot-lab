# LearnBot Lab - Project Plan

AI tutor for maritime crew training. The user uploads their own files; LearnBot explains and quizzes only from them. It must work on any readable file of a supported type (section 3), not one fixed book. Research is a separate web mode, always labelled "From the web".
Built from scratch by Hari P (Data Science Intern). Idea inspired by [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) (Apache 2.0); all code here is our own.

Status: Phase 4 (RAG pipeline) closed on 4 Nov 2026 with caveats (section 0); Day 1 (quiz + flashcards) meets the feature gate with caveats (section 5, 4 Nov); next: Day 2 in section 3 · Started 30 Oct 2026

> **Main product rule:** For ANY uploaded file, LearnBot gives only exact answers from that file's text: exact numbers and units, with page and source quote, checked before showing. If not found or unsure: 'Not in this document'. Never guess.

---

## 0. Problem framing

| | |
|---|---|
| **User** | Ship crew, cadets and freshers studying a maritime topic |
| **Problem** | Long rule books are hard to read alone, there is no one to ask doubts, and it is hard to know what you have really learned |
| **Solution** | Upload a file (it is self-checked and self-tested first), then (a) ask doubts and get an explanation with the exact source, (b) take quizzes and use flashcards made from the document, (c) use the notebook, reading mode and book maker, (d) search the web in the separate Research mode |
| **Not in v1** | Login, video, voice, company documents, own backend API, website URLs, YouTube links, weak-topic re-quiz |

### Success metrics (must pass before "done")

| Metric | Target | Baseline (Phase 3, keyword search BM25, no AI) |
|---|---|---|
| Explain: answer comes from the right rule/page | Reported honestly every run (aim: 9 of 10); **not a gate** since 2 Nov 2026, see below | 17/29 (59%) right doc+page in top 1; 23/29 (79%) in top 3 |
| Explain: exact answer (all numbers + key words) in the top result | (tracked) | 15/29 (52%) |
| Wrong answers (answer shown is not supported by its piece) | 0 | 7 wrong + 4 missed (+1 correct, other source) |
| Quiz: correct answer is supported by the source text | 100% (wrong answer keys = 0) | n/a (Day 1) |
| Trap questions (not in the document) | Says "Not in this document" every time | 7/8 (1 trap answered) |
| Answer time | Under 10 s | 2 ms search per question; 22-28 s to read + chunk the 3 PDFs once |
| Automated tests | All pass before every push | 171 pass |

Baseline details and every failed question: `eval/results.md`. Phase 4 must beat these numbers on the same eval set.

**Phase 4 pass gate (Hari's decision, 2 Nov 2026):** wrong = 0 + every trap "Not in this document" + max answer time under 10 s, on all three sets: the 29 eval questions, the 10 hold-out questions (step 7) and the new public PDF (step 8). Right page is reported honestly in every run but is not a gate.

Why: the product promise is "exact answer with its source, or 'Not in this document'". A missed answer is safe (the user is told it is not found); a wrong answer is not. Reaching 9/10 right page now depends on accepting paraphrased questions that share no word with their quote (NAV-11, BG-08), and no local check could do that safely: both re-rankers and the embedding model scored those right quotes below wrong-number and trap quotes (`eval/results.md`, topic threshold sections). Loosening the proof to reach 9/10 would risk wrong answers, which breaks the main product rule. A second AI judging the answer was rejected: code must prove the answer.

**Phase 4 closed (Hari's decision, 4 Nov 2026) on the gate numbers:**

| Set | Wrong | Traps refused | Not tested | Slowest | Right page (not a gate) |
|---|---|---|---|---|---|
| Eval (29 + 8 traps) | 0 | 8/8 | 0 | 9.0 s | 22/29 |
| Hold-out (10 + 2 traps) | 0 (original score: wrong 1) | 2/2 | 0 | 3.0 s | 7/10 |
| New PDF `osha3124.pdf` (5 + 2 traps) | 0 | 2/2 | 0 | 8.1 s | 3/5 |

Caveats:

- **Not one clean run per set.** Eval: NAV-02 and NAV-08 got "AI busy" and were asked again (same code). New PDF: TRAP-OSHA-01 got "AI busy" and was asked again (same code).
- **Hold-out changed after the run.** p.28 was added to HO-CP-01 after the run; the original score was wrong 1. The answer shown was exact and on p.28, but the row listed only p.17. The new checker review step lists such pages before a run.
- **4th PDF not re-run.** Eval and hold-out ran with 3 PDFs in `data/raw`. `osha3124.pdf` now shares the search, and those two sets have not been re-run with it.
- **"AI busy" can still happen.** Gemini often timed out or gave 503 on 3-4 Nov, and a fallback can run out of the 9 s budget. It is never a wrong answer, but the user gets no answer. It happened again in the live timing test (OSHA-01, 9.0 s).
- **Re-ranker can be slow.** It took 1.0-3.9 s per question on battery with 2-3 GB RAM free, against about 0.5 s average on 3 Nov. The models then took 104.7 s to load (44.7 s on 3 Nov). The cause is not proven: the plugged-in repeat test was not run, and the power state on 3 Nov was not recorded. No fix was made.
- **Missed answers remain.** Safe refusals, not gate failures: eval 7, hold-out 3, new PDF 2, most of them from the `quote_not_focused` check or paraphrased questions.

---

## 1. Data

LearnBot is upload-based: users bring their own files. The 3 files below are only for testing, chosen for different layouts so nothing is book-specific. All are US government works (public domain). PDFs are not committed; download them into `data/raw/` with the names below. Answers in the eval are for these exact editions.

| File (`data/raw/`) | Document | Edition / date | Official URL | Downloaded | Layout |
|---|---|---|---|---|---|
| `nav_rules.pdf` | USCG Navigation Rules and Regulations Handbook | corrected Aug 2024; 202 pages, 7.2 MB | https://www.navcen.uscg.gov/navigation-rules-amalgamated | 30 Oct 2026 | Rule book; International / Inland on facing pages; Annex I-V; two-column CFR pages 156-166 |
| `boaters_guide.pdf` | USCG "A Boater's Guide to the Federal Requirements for Recreational Boats" | revised Nov 2023; 49 pages, 2.4 MB | https://www.uscgboating.org/assets/1/AssetManager/Boaters-Guide-to-Federal-Requirements-for-Receational-Boats-20231108.pdf | 30 Oct 2026 | Booklet; title headings without numbers; few tables |
| `coast_pilot4_ch1.pdf` | NOAA U.S. Coast Pilot 4, Chapter 1 "General Information" | 25 OCT 2026 edition (updated weekly; answers are for this edition); 36 pages, 1.2 MB | https://nauticalcharts.noaa.gov/publications/coast-pilot/files/cp4/CPB4_C01_WEB.pdf | 30 Oct 2026 | Two columns, numbered paragraphs (1), (2) ...; tables |
| `osha3124.pdf` (step 8: new non-maritime PDF) | OSHA "Stairways and Ladders: A Guide to OSHA Rules" (OSHA 3124-12R) | 2003 (old rules are fine: answers are tested from the document only); 15 pages (two booklet pages per PDF page), 159 KB; p.2: "This publication is in the public domain and may be reproduced, fully or partially, without permission" | https://osha.gov/Publications/osha3124.pdf (saved by Hari in a browser; the site blocks scripts) | 3 Nov 2026 | Two-page spreads, columns sometimes interleaved line by line; bullets read as "(cid:2)"; self-check WARNING (cover pages 1 and 15 nearly empty, 103 bullet marks) |

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
Research mode (separate): question -> Tavily web search -> answer labelled "From the web" with source link
```

- **LLM:** Gemini (main) + Groq (fallback when Gemini is busy or out of quota). Own keys in `.env` only.
- **Web search:** Tavily, Research mode only, key `TAVILY_API_KEY` in `.env`. Never mixed into document answers.
- **No own backend API in v1.** Streamlit runs UI + logic. FastAPI can be added later if another app must call LearnBot.
- **Token saving:** send only the top 3-5 pieces, cache generated quizzes, reuse answers to repeated questions, embeddings run locally.

---

## 3. Phases

| # | Phase | Output | Done when |
|---|---|---|---|
| 0 | Problem framing (done) | This plan | Hari agrees |
| 1 | Data + upload self-check (done) | `src/learnbot/pdf_check.py`, `scripts/data_check.py`, reports | Self-check works on any PDF; we know layout, issues, cleaning rules |
| 2 | Eval set first (done) | `eval/explain_questions.csv`, `eval/quiz_rules.md`, trap questions | 20+ questions with expected rule/page |
| 3 | Baseline (done) | Keyword search answer | Baseline score recorded |
| 4 | RAG pipeline (closed with caveats, section 0) | Read, chunk, embed, store, search, answer with source; Gemini + Groq fallback; timeouts | Phase 4 pass gate (section 0) |

### New plan (Hari's decision, 4 Nov 2026)

A simple InfoDeck-like app with chat + quiz + flashcards + notebook + reading mode + book maker + research. This replaces the old phases 5-9. All code is our own. (Now 5 days: Hari added a day for all file types.)

| Day | Build | Done when |
|---|---|---|
| 1 | Quiz + flashcards | Feature gate (below) |
| 2 | Upload self-test + notebook + reading mode | Feature gate (below) |
| 3 | Book maker + research | Feature gate (below) |
| 4 | All file types | 3 questions + 1 trap per file type, wrong 0, under 10 s |
| 5 | Simple UI (ask Hari first) + README, GitHub, resume, LinkedIn | Hari has approved the UI; Hari pushes |

**Feature gate:** 5 questions + 2 traps; wrong 0; every trap refused; every question, card or answer under 10 s (each one by itself, shown as it is ready, not a whole quiz in 10 s); at least 3 of the 5 kept, otherwise the feature is not done, because a feature that drops everything would pass "wrong 0".

Everything else from DeepTutor is dropped.

**Decisions on the older items (Hari, 4 Nov 2026):**

- **Upload self-test: kept, Day 2.** When a new file is uploaded, LearnBot makes 5 questions with quotes from that file and checks that it answers them exactly from the right page. If the self-test fails, the user sees a warning.
- **All file types (old Part B): kept, Day 4.** One upload entry point; the real type is detected from the file content. Supported: PDF with text; scanned PDF and images (.png, .jpg, .jpeg) via OCR; .docx; .pptx; .xlsx and .csv; .txt and .md; .html. Old formats (.doc, .xls, .ppt): convert if a converter is available, else a clear message asking the user to save in the new format. Anything else: a clear "This file type can't be read", never a crash or a guess. Every type gets an exact location label, the same proof rules and the same OK / WARNING / FAIL self-check. Plan + Hari's OK before installing any library or OCR tool.
- **Research: web search with Tavily (`TAVILY_API_KEY`).** A separate mode. Every web answer is labelled "From the web" with the source link and is never mixed into document answers. Document answers keep the main product rule (only from uploaded files). Timeout + friendly message if Tavily fails.
- **Dropped:** weak-topic re-quiz; all of old Part C except web research (website URLs, YouTube links, GitHub repos, code files, `.svg`).

---

## 4. Quality rules (from day 1)

0. **Main product rule:** For ANY uploaded file, LearnBot gives only exact answers from that file's text: exact numbers and units, with page and source quote, checked before showing. If not found or unsure: 'Not in this document'. Never guess.
1. Eval set first, with expected answers. Wrong answers must be 0.
2. General rules only, never one-off fixes for one question.
3. When unsure, say "Not in this document" instead of guessing. Never invent numbers.
4. Timeout + friendly fallback on every external call (Gemini, Groq, Tavily).
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
| 30 Oct 2026 | Phase 3 done: baseline. `chunking.py` (paragraph pieces per page, headings as titles, general rules), `baseline.py` (BM25 over all pieces of all 3 PDFs, threshold `BASELINE_MIN_SCORE` = 11.5 chosen by sweep rule), `evaluate.py` + `scripts/run_baseline.py` -> `eval/results.md`. Result: right page top 1 17/29, top 3 23/29, exact answer 15/29, traps refused 7/8, wrong 8, missed 4. Eval fix found by the baseline: 8 nav_rules questions did not say International/Inland (answer exists in both), wording fixed + new checker rule. `check_eval.py` prints SKIPPED when PDFs are missing. 171 tests pass |
| 30 Oct 2026 | Eval scoring: new outcome "correct, other source" (top-1 piece from another doc/page that contains the row's source_quote, normalised). "Right doc + page" stays strict; "wrong" now means the answer shown is not supported. Baseline re-run: NAV-03 (Coast Pilot p.22 quotes Rule 34(d)) moves from wrong to correct, other source; wrong 7, threshold still 11.5. 174 tests pass |
| 2 Nov 2026 | Phase 4 in progress (NOT done). Built hybrid search (BM25 + bge-small + RRF + rule-set filter + re-ranker: right page in the 5 pieces sent 29/29), Gemini `gemini-3.1-flash-lite` (fastest of 3 timed; `gemini-3.8-flash` gave 504) + Groq `openai/gpt-oss-120b` fallback (no Llama 70B on the account), proof check, answer cache, call limit, 2-failures-in-a-row skip rule. First full eval: right page 23/29, exact 24/29, traps 8/8, **wrong 4**, missed 2, max time 16.8 s. Targets missed: wrong 0, right page 9/10, under 10 s. 41 AI calls used. 230 tests pass |
| 2 Nov 2026 | Phase 4 still NOT done. Added: `accepted_sources` column (every page with the same quote text, found by `scripts/find_accepted_sources.py`, verified by the checker; NAV-13 p.116, NAV-02 p.18, NAV-03/11 p.110 + Coast Pilot p.22); proof rules `unit_missing` ("how many yards" needs yards) and `quote_not_focused` (no other measurements in the quote: found because NAV-10 got a wrong "3 miles" through the old check); prompt v3; main AI timeout 7 s / fallback 15 s. Not done: title words in the topic check (would let a sidelight quote answer a masthead question). Second full run INVALID: Google rejects server deadlines under 10 s, so all 37 Gemini calls failed (400) and Groq answered alone (74 calls, 2 not tested). Fixed: Gemini server deadline 10 s with our own 7 s clock; any error twice in a row skips that AI. Baseline with accepted sources: right page 19/29, wrong 6. 268 tests pass |
| 2 Nov 2026 | Phase 4 still NOT done. General units (`units.py`: a measurement is a number WITH a unit; "33 CFR" is a reference). Smoke test: Gemini answers in 1.4 s with the 10 s deadline. Third full run (valid, prompt v3, 39 AI calls, Gemini answered 35, Groq 2): right page 20/29, exact 20/29, traps 8/8, **wrong 2** (NAV-08 dropped "one"; CP-04 added the meters/feet answer from a 2nd page), missed 7 (3 by `quote_not_focused`: Gemini quoted whole lists), avg 2.9 s, **max 10.1 s** (Gemini 7 s timeout + Groq). Targets missed: wrong 0, right page 9/10, under 10 s. 318 tests pass |
| 2 Nov 2026 | Phase 4 still NOT done. Hari's fixes 1-4, 6, 7 built (general rules, tests): list quote narrowed to the ONE item holding all the answer's numbers + units (lead-in kept, item must be on the page and fit the question by itself); every number of the quote must be in the answer, counts included ("one all-round light"), references ignored; one source unless the question compares; one 9 s time budget per question shared by the AIs (main 5 s); "[Reserved]" rule/paragraph named in a question answered by code with its location. Fix 6 (paraphrase passes on re-ranker score): `scripts/choose_topic_threshold.py` found **no safe threshold** (paraphrased right quotes -11 to -8, bad quotes up to 8; bge-small cosine also fails: 0.51-0.57 vs up to 0.88), so it stays off. Fix 5 (gemini-3.5-flash) waiting: its free-tier limits are not published, only shown in AI Studio. Replay of run 3 replies (0 calls): right page 22/29, **wrong 0**, traps 8/8, missed 7. 351 tests pass |
| 2 Nov 2026 | Phase 4 still NOT done. `BAAI/bge-reranker-base` tested for paraphrases (0 calls): no safe threshold (paraphrased right quotes 0.00-0.10, bad quotes up to 1.00, traps up to 0.97), so the topic check stays words-only; 55 ms per score. Fourth full run **INVALID**: Gemini flash-lite timed out at 5 s on the first 2 questions, so it was switched off for the run; Groq answered alone and hit its per-minute limit 3 times (3 not tested). 39 AI calls. Numbers (not valid): right page 16/29, traps 7/8 tested 7, **wrong 2** (NAV-13: same distress light from boaters_guide p.18 for an "Inland Rules" question; CP-04: "1,852 meters / 6,076.12 feet" from Coast Pilot p.34, real text but not the expected answer), max time 8.5 s (budget works). Waiting for Hari's decisions |
| 2 Nov 2026 | Phase 4 still NOT done. New gate written (wrong 0 + all traps refused + under 10 s on eval, hold-out and new PDF; right page reported, not a gate) in PLAN.md and CLAUDE.md. Added: rule-set source rule (NAV-13), CP-04 other answer (Coast Pilot p.34, checker-verified), AI retried every 5 questions after being switched off, 1-call warm-up, `--fresh`. Fifth full run (warm-up ok 1.1 s, 46 AI calls, Gemini was slow/503 often so Groq answered most): **wrong 0**, traps 8/8, max time 9.0 s, right page 20/29, missed 7, but **2 not tested** (NAV-02, NAV-08: Gemini timeout/503 and Groq out of budget time) -> run INCOMPLETE, not a pass. 391 tests pass |
| 3 Nov 2026 | **Eval set (29 + 8 traps) passes the Phase 4 gate.** Run 5 completed with the same code: only NAV-02 and NAV-08 asked again (first try: Gemini warm-up timeout, 1 call; after 10 min: both **right**, 7.1 s and 7.3 s, Gemini timeout -> Groq; 5 calls, 1 over the 4 asked for because the call limit is checked only before each question). Total: right page 22/29, **wrong 0**, traps **8/8**, not tested 0, max time **9.0 s**. Phase 4 still NOT done: hold-out (step 7) and new PDF (step 8) must pass too |
| 3 Nov 2026 | Call-limit bug fixed: `--max-calls` is now checked before EVERY real AI call (warm-up, Gemini, Groq) by `LLMChain.max_calls`; when it is reached the eval run stops with a clear message and writes no results. The app has no limit (unchanged). Answer logic unchanged: replay of the 37 saved replies gives the same numbers (0 calls). Search timing (0 calls, 37 questions): search + proof avg 0.5-0.6 s, max 1.4 s, almost all re-ranker; 10 s pauses do not slow it; the real path from saved replies takes 0.5-2.0 s. The extra 1-3.5 s seen during live run 5 is not explained by these steps (open question, no fix). 395 tests pass |
| 3 Nov 2026 | Hold-out set (step 7): 10 questions + 2 traps over the 3 PDFs (`eval/holdout_questions.csv`, `eval/holdout_traps.csv`, checker ALL PASS, committed before the run). Gemini failed the warm-up 3 times (timeout, 503, 503), so the eval script now starts the run with the main AI switched off after a failed warm-up (retried every 5 questions). Run once (15 AI calls, Groq answered all 12, Gemini retried twice and failed): right page 6/10, traps 2/2, missed 3 (`quote_not_focused`), max time 3.0 s, **wrong 1** -> hold-out does NOT pass. The wrong one (HO-CP-01) shows "every 4 to 6 minutes" from Coast Pilot p.28 (NOAA Weather Radio, same fact in other words); the row only listed p.17, because accepted sources are found by the same quote text. Waiting for Hari's decision. 397 tests pass |
| 3 Nov 2026 | **Hold-out set passes the Phase 4 gate, after a post-run fix of the row: p.28 added after the run; original score was wrong 1.** Hari chose to add Coast Pilot p.28 (same subject: NOAA Weather Radio repeat interval, same number + unit) to HO-CP-01 `other_answers`; re-scored from saved answers (0 AI calls): right page 7/10, **wrong 0**, traps **2/2**, max time **3.0 s** (live run). Checker improved so this cannot happen silently again: besides same-quote pages it now lists (REVIEW, never added by code) every page with the expected answer's number + unit within 400 characters of at least 2 of the question's key words. On the eval set it lists 9 pages (none judged the same answer: CP-07 nav_rules p.9 is a conversion table, CP-06 nav_rules p.172 is 33 CFR 26.03, the rest share only the number); on the hold-out 2 more (other "2 minutes" signals). No answer logic changed. 399 tests pass |
| 3 Nov 2026 | Step 8: new PDF `osha3124.pdf` (OSHA "Stairways and Ladders", 2003, 15 pages, text PDF, public-domain note, no copyright notice). 5 questions + 2 traps (`eval/newpdf_questions.csv`, `eval/newpdf_traps.csv`, checker ALL PASS, review step 0 pages), committed before the run. Run once (8 AI calls; warm-up Gemini timeout, so Groq answered at first): **wrong 0**, right page 3/5, missed 2 (`quote_not_focused`), trap 1/1 tested refused, max time 8.1 s, but **1 not tested** (TRAP-OSHA-01: Gemini timeout 5 s, then too little of the 9 s budget left for Groq) -> run INCOMPLETE, not a pass. Time outside the AI was 1-4 s per question in this run (0.5 s in the 0-call timing check). Waiting for Hari's decision. 399 tests pass |
| 4 Nov 2026 | New-PDF run completed with the same code: only TRAP-OSHA-01 asked again (2 AI calls): **refused**, 4.0 s. Total: right page 3/5, **wrong 0**, traps **2/2**, not tested 0, slowest **8.1 s**. All three gate sets now meet the numbers: eval (wrong 0, traps 8/8, 9.0 s; 2 questions asked again), hold-out (wrong 0 only after p.28 was added after the run; original score was wrong 1; traps 2/2, 3.0 s), new PDF (1 trap asked again). Not re-run: eval and hold-out were run with 3 PDFs in `data/raw`; `osha3124.pdf` is now a 4th. Live timing (report only, no fix, script outside the project, 5 AI calls, replies not saved): the time outside the AI is almost all the re-ranker: 1.0-3.1 s live, 1.8-3.9 s with 0 AI calls on the same 5 questions (NAV-04 was 0.46 s on 3 Nov), about 15 s of CPU over 10 threads; every other step about 0.1 s or less; model load 104.7 s (44.7 s on 3 Nov). Laptop on battery, Balanced plan, CPU load 2-5 % at question start, 2.4 GB RAM free. Cause not proven. One live question got "AI busy" again (Gemini timeout + Groq out of time, 9.0 s). 399 tests pass |
| 4 Nov 2026 | **Phase 4 closed by Hari on the gate numbers** (wrong 0, all traps refused, under 10 s on eval, hold-out and new PDF), with caveats written in section 0 and `eval/results.md`: questions asked again, hold-out row changed after the run (original score wrong 1), 4th PDF not re-run, "AI busy" can happen, re-ranker slow on battery with low RAM (cause not proven). New 4-day plan written in section 3 (chat + quiz + flashcards + notebook + reading mode + book maker + research; each feature 5 questions + 2 traps, wrong 0); everything else from DeepTutor dropped. Docs only, no code changed. 399 tests pass |
| 4 Nov 2026 | Hari's decisions recorded in this plan and CLAUDE.md: upload self-test kept; all file types kept (old Part B); weak-topic re-quiz and website URL / YouTube (old Part C) dropped; Research = Tavily web search as a separate mode, labelled "From the web" with the source link, never mixed into document answers (`TAVILY_API_KEY` confirmed set in `.env`; value not read out); Definition of done is now per feature: 5 questions + 2 traps, wrong 0, under 10 s. Docs only, no code changed. 399 tests pass |
| 4 Nov 2026 | Hari's OK on the Day 1 plan and the open points: under 10 s applies to each question or card; at least 3 of 5 kept per feature; upload self-test on Day 2; all file types on a new Day 4 (3 questions + 1 trap per type), UI + README move to Day 5; the rest of old Part C dropped. Docs only |
| 4 Nov 2026 | Day 1 quiz built (`study.py`, `quiz.py`, `scripts/make_quiz.py`, `scripts/run_study_eval.py`; chat unchanged) with 5 topics + 2 traps committed before the run. First run (6 AI calls): **gate NOT passed**: kept 2/5, wrong 1, traps 2/2, missed 2, not tested 1, slowest 70.3 s. QUIZ-01: the search models loaded on the first item's clock, so no AI time was left (script bug, AI not asked). QUIZ-04: the question and answer are correct, but the score counts it wrong because the question states the expected "0.87" and the answer does not repeat it. QUIZ-02 and QUIZ-03: dropped correctly (wrong options overlapped the right answer). Both traps were refused by the topic-word check, without the AI. Nothing changed after the run; waiting for Hari's decision. Flashcards not started. 448 tests pass |
| 4 Nov 2026 | **Quiz meets the feature gate, after fixes made after run 1; original score was kept 2/5, wrong 1, not tested 1.** Hari's OK: models load before the clock; numbers stated in the question count in the score. QUIZ-01 asked again (1 AI call), then dropped by a clear bug ("5 years" is inside "15 years"); options now compared as whole words. Re-scored from saved replies (0 calls): kept 3/5, right page 3/5, **wrong 0**, traps 2/2 (by the topic-word check, without the AI), dropped 2, slowest live 7.5 s, 7 AI calls in total. Same 5 topics before and after the fixes, so not a clean first run. 451 tests pass |
| 4 Nov 2026 | **Flashcards meet the feature gate on a clean first run:** topics committed before the run, nothing changed after it (`flashcards.py`, `scripts/make_flashcards.py`, 7 AI calls): kept 4/5, right page 4/5, **wrong 0**, traps 2/2, dropped 1 (`quote_not_focused`), slowest 7.3 s. Caveats: all 4 Day 1 traps were refused by the topic-word check, so the AI was never tested on a trap; section labels can be off on two-page spreads (CARD-01). Try-out: a quiz on "fixed ladders" kept 0 of 4 tries and said "Not in this document" though the document covers the topic (safe, but the checks can drop a lot). Day 1 used 22 of the 35 AI calls allowed. 459 tests pass |
| 6 Nov 2026 | Hari approved the "5 years" / "15 years" fix. When a quiz or flashcard set keeps nothing, the commands now say the words were found but nothing could be proved, instead of "Not in this document" (that message stays when the words are not in the document, and for single items in the feature test, so the gate is unchanged). No prompt change. Harder traps from Day 2: all the words are in the document, the answer is not. |
