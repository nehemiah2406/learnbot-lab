# LearnBot Lab - project memory for Claude Code

## What this is
LearnBot is an AI tutor for maritime crew training, built from scratch by Hari (data science intern, beginner). Users upload a training file, ask doubts (answers with source rule/page), and use quizzes, flashcards, notebook, reading mode and book maker made from it. Research is a separate web mode. Idea inspired by HKUDS/DeepTutor; do NOT copy its code. Full plan: PLAN.md.

## Stack
- Python 3.13, Streamlit UI, code in src/learnbot/, tests in tests/, scripts in scripts/, eval in eval/
- PDF reading: pdfplumber
- Embeddings: local sentence-transformers; vector store: ChromaDB (local, storage/)
- LLM: Gemini (main) + Groq (fallback). Keys and model names in .env (template .env.example)
- Web search (Research mode only): Tavily, key TAVILY_API_KEY in .env
- Test documents: 3 public US government PDFs in data/raw/ (nav_rules.pdf, boaters_guide.pdf, coast_pilot4_ch1.pdf; NOT committed). Links and editions: PLAN.md Data section. LearnBot must work for ANY uploaded file of a supported type (PDF today; the full list and plan: PLAN.md section 3); no file-specific code.

## Product rules (never break)
1. For ANY uploaded file, LearnBot gives only exact answers from that file's text: exact numbers and units, with page and source quote, checked before showing. If not found or unsure: 'Not in this document'. Never guess.
2. Every answer and every quiz question shows its source (rule or section, and page).
3. A quiz question is kept only if its correct answer is supported by the source text; otherwise drop it.
4. Numbers, distances, lights and signals must be EXACT as in the document. Never invent or round.
5. Research is a separate mode. Every web answer is labelled "From the web" with its source link and is never mixed into document answers. Document answers keep rule 1 (only from uploaded files).

## Safety rules
- Never print, log, show or commit .env or any API key.
- Never use company documents. Public documents only.
- Do NOT git push. Commit as described in "Git rules"; I push myself.
- Every Gemini/Groq/Tavily call has a timeout and a friendly fallback message.
- Save free quota: ask me before running big LLM jobs or the full eval.

## How to work
- I am a beginner: before a big change, show a short plan in simple English and wait for my OK.
- One phase/feature per task. Keep existing features working.
- Every change: add/update tests, run the full pytest suite (.venv\Scripts\python -m pytest), all must pass.
- End every task with: what changed, test result, how I can try it.
- Windows laptop, PowerShell, VS Code. Use .venv.
- Update the Progress log in PLAN.md after each phase.

## Definition of done
- A feature is done only when ALL tests pass (.venv\Scripts\python -m pytest).
- Each feature also needs its own 5 questions + 2 traps: 0 wrong answers on normal questions and "Not in this document" for every normal trap question ("Not in your notebook" in the notebook, "Not on this page" in reading mode, "Not found on the web pages checked" in research), every answer, question or card under 10 s by itself, at least 3 of the 5 kept. Hard traps (all the words are in the document, the answer is not) are reported honestly, not a gate; known limit in PLAN.md section 0. All file types (PLAN.md Day 4): 3 questions + 1 trap per type instead. Right source (rule/page) is reported honestly every run but is not a gate (reason: PLAN.md Success metrics).
- Never say "done" with a failing test or a missed metric. Fix it first, then show the real numbers.

## Git rules
- After a change is finished and all tests pass, commit it yourself: one commit per change, clear message.
- Before every commit run `git status` and check that no PDF, .env, API key, data/ or storage/ file is staged.
- NEVER run git push. Hari pushes.
