"""Compare search options on the eval set (no AI calls) and save a section in eval/results.md.

Run:  .venv\\Scripts\\python scripts\\compare_search.py
Measures what the AI will see: is the right doc + page among the pieces sent?
Choice rule (fixed before looking at single questions): most questions with the right
page among the pieces sent; tie -> more right in top 1; tie -> more compare questions with
both pages sent; tie -> the simpler option.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot import config  # noqa: E402
from learnbot.eval_check import load_rows, row_pages  # noqa: E402
from learnbot.evaluate import on_right_page  # noqa: E402
from learnbot.index import Embedder, Library, VectorStore  # noqa: E402
from learnbot.report import replace_section  # noqa: E402
from learnbot.search import CrossEncoderReranker, Searcher  # noqa: E402

DATA_DIR = Path("data/raw")
RESULTS = Path("eval/results.md")
EMBED_MODELS = ["sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-small-en-v1.5"]
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"


class Hit:  # on_right_page() expects an object with .chunk
    def __init__(self, chunk):
        self.chunk = chunk


def measure(searcher, rows, k):
    top1 = topk = both = 0
    seconds = []
    for row in rows:
        start = time.perf_counter()
        pieces = searcher.search(row["question"], k=k)
        seconds.append(time.perf_counter() - start)
        top1 += bool(pieces) and on_right_page(row, Hit(pieces[0]))
        topk += any(on_right_page(row, Hit(c)) for c in pieces)
        if row["type"] == "compare":
            sent = {(c.doc, c.page) for c in pieces}
            both += all((row["doc"], p) in sent for p in row_pages(row))
    return {"top1": top1, "topk": topk, "both": both, "ms": 1000 * sum(seconds) / len(seconds)}


def main():
    sys.stdout.reconfigure(errors="replace")
    rows = load_rows("eval/explain_questions.csv")
    needed = sorted({r["doc"] for r in rows})
    missing = [d for d in needed if not (DATA_DIR / d).is_file()]
    if missing:
        print(f"SKIPPED: PDF(s) not in data/raw: {', '.join(missing)} (see PLAN.md Data section)")
        return 0
    pdfs = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() == ".pdf")
    k = config.PIECES_TO_LLM
    n, n_compare = len(rows), sum(r["type"] == "compare" for r in rows)

    options = []  # (name, parts, searcher); parts = how many pieces of machinery
    library = Library.load(pdfs)
    options.append(("BM25", 1, Searcher(library, "bm25", use_rule_sets=False)))
    options.append(("BM25 + rule set", 2, Searcher(library, "bm25")))
    reranker = CrossEncoderReranker(RERANK_MODEL)
    for model in EMBED_MODELS:
        start = time.perf_counter()
        lib = Library.load(pdfs, VectorStore(Embedder(model)))
        print(f"{model}: index ready in {time.perf_counter() - start:.1f} s")
        short = model.split("/")[-1]
        options += [
            (f"Embeddings {short}", 1, Searcher(lib, "embed", use_rule_sets=False)),
            (f"Embeddings {short} + rule set", 2, Searcher(lib, "embed")),
            (f"Hybrid RRF ({short})", 2, Searcher(lib, "hybrid", use_rule_sets=False)),
            (f"Hybrid RRF ({short}) + rule set", 3, Searcher(lib, "hybrid")),
            (f"Hybrid RRF ({short}) + rule set + re-ranker", 4, Searcher(lib, "hybrid", reranker=reranker)),
        ]

    results = []
    for name, parts, searcher in options:
        m = measure(searcher, rows, k)
        results.append((name, parts, m))
        print(f"{name}: right page in top {k} {m['topk']}/{n}, top 1 {m['top1']}/{n}, "
              f"compare both pages {m['both']}/{n_compare}, {m['ms']:.0f} ms")
    best = max(results, key=lambda r: (r[2]["topk"], r[2]["top1"], r[2]["both"], -r[1]))

    rules = options[1][2].rule_sets
    named = [r for r in rows if rules.asked(r["question"])]
    allowed = sum(rules.allowed(r["question"], r["doc"], int(r["page"])) for r in named)
    lines = [
        "## Phase 4 search choice (no AI)",
        "",
        f"All {len(pdfs)} PDFs in one index ({len(library.chunks)} pieces). The AI gets the top "
        f"**{k}** pieces, so the main number is \"right doc + page among the {k} pieces sent\".",
        "Choice rule, fixed before looking at single questions: most right in the pieces sent; "
        "tie -> more right in top 1; tie -> the simpler option. The first run ended in an exact tie "
        "on all three, so one tie-break was added before \"simpler\": more compare questions with "
        "both pages sent (a compare answer needs both pages).",
        "",
        f"| Search | Right page in top {k} | Right page top 1 | Compare: both pages sent | Avg search time |",
        "|---|---|---|---|---|",
    ]
    for name, _, m in results:
        mark = " **← chosen**" if name == best[0] else ""
        lines.append(f"| {name}{mark} | {m['topk']}/{n} | {m['top1']}/{n} | {m['both']}/{n_compare} | {m['ms']:.0f} ms |")
    lines += [
        "",
        f"Rule-set check: {len(named)} questions name one rule set; their expected page has that "
        f"rule set's label in {allowed}/{len(named)} cases (labels come from page headings).",
    ]
    replace_section(RESULTS, "phase4-search", "\n".join(lines))
    print(f"Best by the rule: {best[0]}")
    print(f"Rule-set labels: expected page allowed for {allowed}/{len(named)} questions naming a rule set")
    print(f"Saved {RESULTS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
