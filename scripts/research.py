"""Research mode: ask the web. Separate from your documents.

Run:  .venv\\Scripts\\python scripts\\research.py "What wind speeds does a gale warning indicate?"

Uses 1 Tavily search and 1-2 AI calls. Only the question is sent to the web search.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.answer import AI_BUSY_STATUS  # noqa: E402
from learnbot.llm import default_chain  # noqa: E402
from learnbot.research import AI_BUSY_WEB, research, show  # noqa: E402


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    args = parser.parse_args()
    chain = default_chain()
    if not chain.providers:
        print(AI_BUSY_WEB)
        return 1
    ans = research(args.question, chain)
    print(show(ans))
    if ans.status == AI_BUSY_STATUS:
        print(f"(Failure type: {ans.reason}. Saved in storage/research/failures.jsonl)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
