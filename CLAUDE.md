# LearnBot Lab - project memory for Claude Code

## What this is
LearnBot is an AI tutor for maritime crew training, built from scratch by Hari (data science intern, beginner). Users upload a training PDF, ask doubts (answers with source rule/page), take quizzes generated from the document, and see weak topics. Idea inspired by HKUDS/DeepTutor; do NOT copy its code. Full plan: PLAN.md.

## Stack
- Python 3.13, Streamlit UI, code in src/learnbot/, tests in tests/, scripts in scripts/, eval in eval/
- PDF reading: pdfplumber
- Embeddings: local sentence-transformers; vector store: ChromaDB (local, storage/)
- LLM: Gemini (main) + Groq (fallback). Keys and model names in .env (template .env.example)
- Main test document: data/raw/nav_rules.pdf (USCG Navigation Rules handbook, public, NOT committed)

## Product rules (never break)
1. Explanations and quiz answers come ONLY from the uploaded document. If not found: "Not in this document."
2. Every answer and every quiz question shows its source (rule number and page).
3. A quiz question is kept only if its correct answer is supported by the source text; otherwise drop it.
4. Numbers, distances, lights and signals must be EXACT as in the document. Never invent or round.

## Safety rules
- Never print, log, show or commit .env or any API key.
- Never use company documents. Public documents only.
- Do NOT git push. Commit only when I ask; I push myself.
- Every Gemini/Groq call has a timeout and a friendly fallback message.
- Save free quota: ask me before running big LLM jobs or the full eval.

## How to work
- I am a beginner: before a big change, show a short plan in simple English and wait for my OK.
- One phase/feature per task. Keep existing features working.
- Every change: add/update tests, run the full pytest suite (.venv\Scripts\python -m pytest), all must pass.
- End every task with: what changed, test result, how I can try it.
- Windows laptop, PowerShell, VS Code. Use .venv.
- Update the Progress log in PLAN.md after each phase.
