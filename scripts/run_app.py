"""Start the LearnBot page on this laptop only.

Run:  .venv\\Scripts\\python scripts\\run_app.py
Then open http://127.0.0.1:8765 in your browser. Press Ctrl+C here to stop it.

The page lists the files in data/uploads. Adding a new file uses about 10-20 AI calls (its
automatic self-test, once per file); each question uses 1-2. Public documents only.
"""

import argparse
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.webapp import HOST, App, make_server  # noqa: E402


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-calls", type=int, help="stop using the AI after this many calls (default: no limit)")
    parser.add_argument("--open", action="store_true", help="open the page in the browser once the server listens")
    args = parser.parse_args()

    url = f"http://{HOST}:{args.port}"
    app = App(max_calls=args.max_calls)
    try:
        server = make_server(app, args.port)
    except OSError:
        print(f"Port {args.port} is in use. LearnBot may already be running, or try --port 8766.")
        if args.open:
            webbrowser.open(url)  # most likely LearnBot is already running: show it
        return 1
    app.start()
    print(f"LearnBot is starting. Open {url} in your browser. Close this window or press Ctrl+C here to stop.")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("LearnBot stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
