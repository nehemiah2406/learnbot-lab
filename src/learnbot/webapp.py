"""The LearnBot page: one HTML file served by Python's built-in http.server, on this laptop only.

The page calls the same functions as the commands: upload_file (self-check, automatic self-test)
and answer_within (chat pipeline + proof check). Every added file shows only "Uploaded": the
self-test still runs once per file, and its result and any self-check warning go to
config.LOG_DIR/selftest.log, never to the page. A file that cannot be read shows a clear error.
Safety:

- The server listens on 127.0.0.1 only.
- Requests must name this server as their Host, so a web page cannot reach it through a
  look-alike address. Every POST must carry X_LEARNBOT_HEADER and, if it has an Origin, this
  server's own: other web sites cannot send that header without asking first, and nothing here
  says yes. So another site in the browser cannot upload files or spend AI quota.
- An error shows a friendly message, never the error's own text. Questions are not logged.
"""

import json
import queue
import shutil
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from learnbot import config
from learnbot.answer import AI_BUSY_STATUS, ANSWERED, answer_is_quote, answer_within
from learnbot.baseline import NOT_FOUND
from learnbot.index import Embedder, Library, VectorStore, file_hash
from learnbot.llm import CallLimitReached, default_chain
from learnbot.proof import shown_quote, shown_where
from learnbot.search import Searcher, default_searcher
from learnbot.selftest import self_test_once
from learnbot.upload import upload_file

HOST = "127.0.0.1"
PAGE = Path(__file__).with_name("static") / "index.html"
X_LEARNBOT_HEADER = "X-LearnBot"
MAX_QUESTION_CHARS = 1000
FROM_DOCUMENT = "From your document"
STILL_LOADING = "LearnBot is still starting. Please try again in a minute."
FILE_BEING_CHECKED = "LearnBot is getting a new file ready. Please try again in a minute."
UPLOADED, ADDING = "Uploaded", "Adding"
AI_NOT_SET = "The AI is not set up: no AI key was found."
AI_LIMIT = "The AI call limit for this session is used up. Please restart LearnBot."
UPLOAD_FAILED = "This file could not be added. Please try again."
CHOOSE_DOCUMENT = "Please add or choose a document first."
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                               "connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def real_searcher(paths, previous=None):
    """The search over these files. The models load once, on the first call."""
    if previous is None:
        searcher = default_searcher(Library.load(paths, VectorStore(Embedder())))
    else:
        library = Library.load(paths, previous.library.store)
        searcher = Searcher(library, config.SEARCH_METHOD, use_rule_sets=True, reranker=previous.reranker)
    searcher.search("load the models")
    return searcher


def card(ans):
    """What the page shows for one Answer. A refusal has no text: its red label says it."""
    if ans.status == AI_BUSY_STATUS:
        return busy_card(ans.text)
    if ans.status != ANSWERED:
        return {"kind": "refused", "label": NOT_FOUND, "text": "", "sources": [], "showQuote": False}
    sources = [{"doc": s["doc"], "location": shown_where(s), "section": s.get("title", ""), "quote": shown_quote(s)}
               for s in ans.sources]
    return {"kind": "document", "label": FROM_DOCUMENT, "text": ans.text, "sources": sources,
            "showQuote": not answer_is_quote(ans)}


def busy_card(text):
    return {"kind": "busy", "label": "Please try again", "text": text, "sources": [], "showQuote": False}


class App:
    def __init__(self, upload_dir=None, storage_dir=None, make_chain=default_chain, make_searcher=real_searcher,
                 max_calls=None, log_dir=None):
        self.upload_dir = Path(upload_dir or config.UPLOAD_DIR)
        self.storage_dir = storage_dir
        self.log_path = Path(log_dir or config.LOG_DIR) / "selftest.log"
        self.make_chain, self.make_searcher, self.max_calls = make_chain, make_searcher, max_calls
        self.chain = self.searcher = None
        self.ready = threading.Event()
        self.ai_lock = threading.Lock()  # one AI job at a time: a question or a self-test
        self.jobs = queue.Queue()
        self.active = set()  # names of the files still being added or self-tested
        self.notices = []  # [{file, message, kind}], newest last
        self.state_lock = threading.Lock()

    def start(self):
        threading.Thread(target=self.load, daemon=True).start()
        threading.Thread(target=self.work, daemon=True).start()

    def paths(self):
        if not self.upload_dir.is_dir():
            return []
        return sorted(p for p in self.upload_dir.iterdir() if p.is_file())

    def load(self):
        """Load the models and the uploaded files. A failure leaves the page saying it is starting."""
        try:
            self.chain = self.make_chain()
            self.chain.max_calls = self.max_calls
            self.searcher = self.make_searcher(self.paths())
            self.ready.set()
        except Exception:  # noqa: BLE001 - the error's own text is never shown
            self.notify("", "LearnBot could not start. Please close it and start it again.", "error")

    def notify(self, name, message, kind):
        with self.state_lock:
            self.notices = (self.notices + [{"file": name, "message": message, "kind": kind}])[-20:]

    def log(self, name, message):
        """One line in the self-test log. A log that cannot be written never stops the page."""
        line = f"{datetime.now().isoformat(timespec='seconds')} | {name} | {message}\n"
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.state_lock, open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def status(self):
        """Everything the page needs to draw the sidebar."""
        with self.state_lock:
            active, notices = set(self.active), list(self.notices)
        documents = [{"name": path.name, "badge": UPLOADED, "badgeKind": "good"} for path in self.paths()]
        known = {d["name"] for d in documents}
        documents += [{"name": name, "badge": ADDING, "badgeKind": "busy"} for name in sorted(active - known)]
        return {"ready": self.ready.is_set(), "working": bool(active), "documents": documents, "notices": notices}

    def add_upload(self, name, data):
        """Queue one uploaded file. The page polls status() for the result."""
        folder = Path(tempfile.mkdtemp(prefix="learnbot-upload-"))
        (folder / name).write_bytes(data)
        with self.state_lock:
            self.active.add(name)
        self.jobs.put((name, folder))

    def work(self):
        self.ready.wait()
        while True:
            name, folder = self.jobs.get()
            with self.ai_lock:
                try:
                    self.process(name, folder / name)
                except Exception:  # noqa: BLE001 - a bad file must not stop the page
                    self.notify(name, UPLOAD_FAILED, "error")
            shutil.rmtree(folder, ignore_errors=True)
            with self.state_lock:
                self.active.discard(name)

    def run_self_test(self, stored):
        """The search now includes the stored file, then the automatic self-test (once per file).
        The file stays added if the test cannot finish: only the log says so."""
        self.searcher = self.make_searcher(self.paths(), self.searcher)
        try:
            test = self_test_once(stored.name, file_hash(stored), self.searcher.for_document(stored.name), self.chain,
                                  self.storage_dir)
        except CallLimitReached:
            self.log(stored.name, "self-test not finished: AI call limit used up")
            return None
        except Exception as problem:  # noqa: BLE001 - the error's kind only, never its text
            self.log(stored.name, f"self-test not finished: {type(problem).__name__}")
            return None
        saved = ", saved result" if test.from_saved else ""
        self.log(stored.name, f"self-test {test.verdict}: {test.passed}/{test.wanted}, dropped {test.dropped}{saved}")
        return test

    def process(self, name, path):
        result = upload_file(path, self.run_self_test, self.upload_dir)
        if result.problem:
            self.notify(name, result.problem, "error")
        elif result.check.reasons:
            self.log(name, "self-check: " + "; ".join(result.check.reasons))

    def ask(self, name, question):
        """The card for one question, asked only inside the chosen file."""
        if not self.ready.is_set():
            return busy_card(STILL_LOADING)
        if not self.chain.providers:
            return busy_card(AI_NOT_SET)
        if name not in {p.name for p in self.paths()}:
            return busy_card(CHOOSE_DOCUMENT)
        if not self.ai_lock.acquire(blocking=False):
            return busy_card(FILE_BEING_CHECKED)
        try:
            return card(answer_within(question, self.searcher.for_document(name), self.chain, NOT_FOUND))
        except CallLimitReached:
            return busy_card(AI_LIMIT)
        except Exception:  # noqa: BLE001 - the error's own text is never shown
            return busy_card("Something went wrong with this question. Please try again.")
        finally:
            self.ai_lock.release()


def clean_file_name(name):
    """The bare file name, or "" if it could reach outside the folder or is not a normal name."""
    name = (name or "").strip()
    bare = Path(name.replace("\\", "/")).name
    if bare != name or bare in (".", "..") or any(ord(c) < 32 or c in '<>:"|?*' for c in bare):
        return ""
    return bare


class Handler(BaseHTTPRequestHandler):
    app = None
    server_version = "LearnBot"
    sys_version = ""

    def log_message(self, *args):
        """Nothing is logged: paths could hold file names."""

    def send(self, status, body, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status=200):
        self.send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def send_problem(self, status, message):
        self.close_connection = True  # any body not read must not be taken as the next request
        self.send_json({"error": message}, status)

    def own_addresses(self):
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def host_is_ours(self):
        return self.headers.get("Host", "") in self.own_addresses()

    def post_is_ours(self):
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc not in self.own_addresses():
            return False
        return self.headers.get(X_LEARNBOT_HEADER) == "1"

    def body_length(self, limit):
        """The request's body size, or None (after answering) if it is missing or too big."""
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_problem(411, "This request has no size.")
            return None
        if length < 0 or length > limit:
            self.send_problem(413, f"The limit is {config.MAX_FILE_MB} MB. Please choose a smaller file.")
            return None
        return length

    def do_GET(self):
        if not self.host_is_ours():
            self.send_problem(403, "Not allowed.")
        elif self.path == "/":
            self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self.send_json(self.app.status())
        else:
            self.send_problem(404, "Not found.")

    def do_POST(self):
        if not self.host_is_ours() or not self.post_is_ours():
            self.send_problem(403, "Not allowed.")
            return
        url = urlparse(self.path)
        if url.path == "/api/ask":
            self.handle_ask()
        elif url.path == "/api/upload":
            self.handle_upload(parse_qs(url.query).get("name", [""])[0])
        else:
            self.send_problem(404, "Not found.")

    def handle_ask(self):
        length = self.body_length(MAX_QUESTION_CHARS * 8)
        if length is None:
            return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            document, question = str(data["document"]), str(data["question"]).strip()
        except (ValueError, KeyError, TypeError):
            self.send_problem(400, "This question could not be read.")
            return
        if not question or len(question) > MAX_QUESTION_CHARS:
            self.send_problem(400, f"Please ask a question of at most {MAX_QUESTION_CHARS} characters.")
            return
        self.send_json(self.app.ask(document, question))

    def handle_upload(self, name):
        name = clean_file_name(name)
        if not name:
            self.send_problem(400, "This file name can't be used.")
            return
        length = self.body_length(config.MAX_FILE_MB * 1024 * 1024)
        if length is None:
            return
        self.app.add_upload(name, self.rfile.read(length))
        self.send_json({"accepted": name}, 202)


def make_server(app, port=0):
    """The server, listening on this laptop only. port 0: any free port."""
    handler = type("AppHandler", (Handler,), {"app": app})
    return ThreadingHTTPServer((HOST, port), handler)
