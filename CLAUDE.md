# LearnBot Lab - project memory for Claude Code

## What this is
LearnBot is an AI tutor for maritime crew training, built from scratch by Hari (data science intern, beginner). Users upload a training PDF, ask doubts (answers with source rule/page), take quizzes generated from the document, and see weak topics. Idea inspired by HKUDS/DeepTutor; do NOT copy its code. Full plan: PLAN.md.

## Stack
- Python 3.13, Streamlit UI, code in src/learnbot/, tests in tests/, scripts in scripts/, eval in eval/
- PDF reading: pdfplumber
- Embeddings: local sentence-transformers; vector store: ChromaDB (local, storage/)
- LLM: Gemini (main) + Groq (fallback). Keys and model names in .env (template .env.example)
- Test documents: 3 public US government PDFs in data/raw/ (nav_rules.pdf, boaters_guide.pdf, coast_pilot4_ch1.pdf; NOT committed). Links and editions: PLAN.md Data section. LearnBot must work for ANY uploaded PDF; no file-specific code.

## Product rules (never break)
1. For ANY uploaded file, LearnBot gives only exact answers from that file's text: exact numbers and units, with page and source quote, checked before showing. If not found or unsure: 'Not in this document'. Never guess.
2. Every answer and every quiz question shows its source (rule or section, and page).
3. A quiz question is kept only if its correct answer is supported by the source text; otherwise drop it.
4. Numbers, distances, lights and signals must be EXACT as in the document. Never invent or round.

## Safety rules
- Never print, log, show or commit .env or any API key.
- Never use company documents. Public documents only.
- Do NOT git push. Commit as described in "Git rules"; I push myself.
- Every Gemini/Groq call has a timeout and a friendly fallback message.
- Save free quota: ask me before running big LLM jobs or the full eval.

## How to work
- I am a beginner: before a big change, show a short plan in simple English and wait for my OK.
- One phase/feature per task. Keep existing features working.
- Every change: add/update tests, run the full pytest suite (.venv\Scripts\python -m pytest), all must pass.
- End every task with: what changed, test result, how I can try it.
- Windows laptop, PowerShell, VS Code. Use .venv.
- Update the Progress log in PLAN.md after each phase.

## Definition of done
- A phase is done only when ALL tests pass (.venv\Scripts\python -m pytest).
- From Phase 4 onward it also needs the eval to meet every success metric in PLAN.md: 0 wrong answers, 9/10+ correct source (rule/page), "Not in this document" for every trap question.
- Never say "done" with a failing test or a missed metric. Fix it first, then show the real numbers.

## Git rules
- After a change is finished and all tests pass, commit it yourself: one commit per change, clear message.
- Before every commit run `git status` and check that no PDF, .env, API key, data/ or storage/ file is staged.
- NEVER run git push. Hari pushes.
