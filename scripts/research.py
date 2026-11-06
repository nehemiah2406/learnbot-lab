"""Research mode: ask the web. Separate from your documents.

Run:  .venv\\Scripts\\python scripts\\research.py "What wind speeds does a gale warning indicate?"

Uses 1 Tavily search and 1-2 AI calls. Only the question is sent to the web search.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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
    print(show(research(args.question, chain)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
