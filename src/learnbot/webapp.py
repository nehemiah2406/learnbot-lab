"""The LearnBot page: one HTML file served by Python's built-in http.server, on this laptop only.

The page calls the same functions as the commands: upload_file (self-check, automatic self-test),
answer_within (chat pipeline + proof check), make_question, make_card, Notebook, view_page,
ask_page, make_book and research. Quiz and Flashcards make one item per click, so each shows as
soon as it is ready. Every added file shows only "Uploaded": the
self-test still runs once per file, and its result and any self-check warning go to
config.LOG_DIR/selftest.log, never to the page. A file that cannot be read shows a clear error.
Only an item the server made and checked can be saved to the notebook: the page sends its id,
never its text. Web answers cannot be saved there.
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
import re
import shutil
import tempfile
import threading
import uuid
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from learnbot import config, study
from learnbot.answer import AI_BUSY_STATUS, ANSWERED, REFUSED, Answer, answer_is_quote, answer_within
from learnbot.baseline import NOT_FOUND
from learnbot.book import make_book, save_book
from learnbot.flashcards import make_card
from learnbot.index import Embedder, Library, VectorStore, file_hash
from learnbot.llm import CallLimitReached, default_chain
from learnbot.notebook import NOT_IN_NOTEBOOK, YOUR_NOTE, Notebook
from learnbot.proof import shown_quote, shown_where
from learnbot.quiz import make_question
from learnbot.reading import NOT_ON_PAGE, ask_page, view_page
from learnbot.research import FROM_THE_WEB, NOT_FOUND_WEB, research, tavily_search
from learnbot.search import Searcher, default_searcher
from learnbot.selftest import self_test_once
from learnbot.upload import upload_file

HOST = "127.0.0.1"
PAGE = Path(__file__).with_name("static") / "index.html"
X_LEARNBOT_HEADER = "X-LearnBot"
MAX_QUESTION_CHARS = 1000
MAX_REMEMBERED = 200  # recent checked items that can still be answered or saved
MAX_UNREAD_BYTES = 1024 * 1024  # read this much of a refused request before closing it
FROM_DOCUMENT = "From your document"
STILL_LOADING = "LearnBot is still starting. Please try again in a minute."
FILE_BEING_CHECKED = "LearnBot is getting a new file ready. Please try again in a minute."
UPLOADED, ADDING = "Uploaded", "Adding"
AI_NOT_SET = "The AI is not set up: no AI key was found."
AI_LIMIT = "The AI call limit for this session is used up. Please restart LearnBot."
UPLOAD_FAILED = "This file could not be added. Please try again."
CHOOSE_DOCUMENT = "Please add or choose a document first."
ITEM_GONE = "This item is too old. Please make a new one."
WENT_WRONG = "Something went wrong. Please try again."
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


def source_view(source):
    """One source as the page shows it. A web source has a link instead of a location."""
    doc = str(source["doc"])
    if doc.startswith(("http://", "https://")):
        return {"doc": doc, "link": doc, "location": "", "section": source.get("title", ""), "quote": shown_quote(source)}
    return {"doc": doc, "location": shown_where(source), "section": source.get("title", ""), "quote": shown_quote(source)}


def refused_card(label=NOT_FOUND, text=""):
    return {"kind": "refused", "label": label, "text": text, "sources": [], "showQuote": False}


def card(ans, refusal=NOT_FOUND, kind="document", label=FROM_DOCUMENT):
    """What the page shows for one Answer. A refusal has no text: its red label says it."""
    if ans.status == AI_BUSY_STATUS:
        return busy_card(ans.text)
    if ans.status != ANSWERED:
        return refused_card(refusal)
    return {"kind": kind, "label": label, "text": ans.text, "sources": [source_view(s) for s in ans.sources],
            "showQuote": not answer_is_quote(ans)}


def busy_card(text):
    return {"kind": "busy", "label": "Please try again", "text": text, "sources": [], "showQuote": False}


class BadRequest(ValueError):
    """A request the page can explain to the user with this message."""


class App:
    def __init__(self, upload_dir=None, storage_dir=None, make_chain=default_chain, make_searcher=real_searcher,
                 max_calls=None, log_dir=None, search_web=tavily_search):
        self.upload_dir = Path(upload_dir or config.UPLOAD_DIR)
        self.storage_dir = storage_dir
        self.search_web = search_web
        self.log_path = Path(log_dir or config.LOG_DIR) / "selftest.log"
        self.make_chain, self.make_searcher, self.max_calls = make_chain, make_searcher, max_calls
        self.chain = self.searcher = None
        self.ready = threading.Event()
        self.ai_lock = threading.Lock()  # one AI job at a time: a question or a self-test
        self.jobs = queue.Queue()
        self.active = set()  # names of the files still being added or self-tested
        self.notices = []  # [{file, message, kind}], newest last
        self.state_lock = threading.Lock()
        self.recent = {}  # id -> {kind, item, question}: checked items, newest last
        self.used_pieces = {}  # (kind, file, topic) -> pieces already gone through

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
        return {"ready": self.ready.is_set(), "working": bool(active), "documents": documents, "notices": notices,
                "quizScore": self.quiz_score()}

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

    def with_ai(self, job, name=None):
        """job() -> reply, one AI job at a time. Any problem is a friendly card. name: the chosen file."""
        if not self.ready.is_set():
            return busy_card(STILL_LOADING)
        if not self.chain.providers:
            return busy_card(AI_NOT_SET)
        if name is not None and name not in {p.name for p in self.paths()}:
            return busy_card(CHOOSE_DOCUMENT)
        if not self.ai_lock.acquire(blocking=False):
            return busy_card(FILE_BEING_CHECKED)
        try:
            return job()
        except CallLimitReached:
            return busy_card(AI_LIMIT)
        except BadRequest as problem:
            return busy_card(str(problem))
        except Exception:  # noqa: BLE001 - the error's own text is never shown
            return busy_card(WENT_WRONG)
        finally:
            self.ai_lock.release()

    def remember(self, kind, item, question=""):
        """Keep a checked item on the server. The page refers to it only by this id."""
        number = uuid.uuid4().hex
        with self.state_lock:
            self.recent[number] = {"kind": kind, "item": item, "question": question}
            while len(self.recent) > MAX_REMEMBERED:
                self.recent.pop(next(iter(self.recent)))
        return number

    def remembered(self, number):
        with self.state_lock:
            entry = self.recent.get(number)
        if entry is None:
            raise BadRequest(ITEM_GONE)
        return entry

    def savable_card(self, kind, ans, question="", refusal=NOT_FOUND):
        shown = card(ans, refusal)
        if ans.status == ANSWERED:
            shown["saveId"] = self.remember(kind, ans, question)
        return shown

    def ask(self, name, question):
        """The card for one question, asked only inside the chosen file."""
        return self.with_ai(lambda: self.savable_card(
            "chat", answer_within(question, self.searcher.for_document(name), self.chain, NOT_FOUND), question), name)

    # --- Quiz and flashcards: one item per click ------------------------------------------
    def next_item(self, kind, name, topic, make_one, tries):
        """(item, dropped): the next item from the pieces not used yet. item None = none kept.
        A busy AI gives the busy item, and its piece is tried again on the next click."""
        searcher = self.searcher.for_document(name)
        if topic:
            pieces = study.topic_pieces(topic, searcher, config.PAGE_STUDY_PIECES)
        else:
            pieces = study.spread_pieces(searcher.chunks, config.PAGE_STUDY_PIECES)
        key = (kind, name, (topic or "").lower())
        position = self.used_pieces.get(key, 0)
        if position >= len(pieces):
            position = 0  # all used: start again (saved replies cost no quota)
        dropped = 0
        for piece in pieces[position:position + tries]:
            item = make_one(topic, searcher, self.chain, [piece])
            if item.status == AI_BUSY_STATUS:
                self.used_pieces[key] = position
                return item, dropped
            position += 1
            self.used_pieces[key] = position
            if item.status == ANSWERED:
                return item, dropped
            dropped += 1
        return None, dropped

    def nothing_kept(self, topic, dropped, noun):
        text = study.nothing_kept(topic, dropped, noun)
        return refused_card(text=text if text != NOT_FOUND else "")

    def quiz(self, name, topic):
        """One quiz question. The right answer stays here until the user chooses an option."""
        def job():
            item, dropped = self.next_item("quiz", name, topic, make_question, config.QUIZ_SET_TRIES_PER_QUESTION)
            if item is None:
                return self.nothing_kept(topic, dropped, "quiz question")
            if item.status != ANSWERED:
                return card(item)
            sources = [{key: value for key, value in source_view(s).items() if key != "quote"} for s in item.sources]
            return {"kind": "quiz", "id": self.remember("quiz", item), "question": item.question,
                    "options": item.options, "sources": sources}
        return self.with_ai(job, name)

    def quiz_answer(self, number, choice):
        """Right or not, the answer's card, and today's score. Only the first choice counts."""
        entry = self.remembered(number)
        if entry["kind"] != "quiz":
            raise BadRequest(ITEM_GONE)
        item = entry["item"]
        if choice not in range(len(item.options)):
            raise BadRequest("Please choose one of the options.")
        with self.state_lock:
            first = "choice" not in entry
            entry.setdefault("choice", choice)
        if first:
            self.add_to_score(entry["choice"] == item.correct)
        return {"right": entry["choice"] == item.correct, "chosen": entry["choice"], "correct": item.correct,
                "card": {**card(item), "saveId": number}, "score": self.quiz_score()}

    def score_path(self):
        return Path(self.storage_dir or config.STORAGE_DIR) / "quiz_score.json"

    def quiz_score(self):
        """{right, asked} today."""
        path = self.score_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except (OSError, ValueError):
            data = {}
        if data.get("date") != date.today().isoformat():
            return {"right": 0, "asked": 0}
        return {"right": data["right"], "asked": data["asked"]}

    def add_to_score(self, right):
        score = self.quiz_score()
        path = self.score_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"date": date.today().isoformat(), "right": score["right"] + int(right),
                                    "asked": score["asked"] + 1}), encoding="utf-8")

    def flashcard(self, name, topic):
        """One flashcard: its front, and the card shown when the user turns it over."""
        def job():
            item, dropped = self.next_item("card", name, topic, make_card, config.STUDY_TRIES_PER_ITEM)
            if item is None:
                return self.nothing_kept(topic, dropped, "flashcard")
            if item.status != ANSWERED:
                return card(item)
            return {"kind": "flashcard", "front": item.question, "card": self.savable_card("card", item)}
        return self.with_ai(job, name)

    # --- Notebook -----------------------------------------------------------------------------
    def notebook_items(self):
        """Saved items, newest first."""
        items = []
        for saved in reversed(Notebook(self.storage_dir).items):
            if saved["kind"] == "note":
                shown = {"kind": "note", "label": YOUR_NOTE, "text": saved["text"], "sources": [], "showQuote": False}
            else:
                shown = card(Answer(ANSWERED, saved["text"], [], sources=saved["sources"]))
            items.append({"id": saved["id"], "question": saved.get("question", ""), "card": shown})
        return {"items": items}

    def notebook_save(self, number):
        entry = self.remembered(number)
        with self.state_lock:
            if not entry.get("saved"):
                try:
                    Notebook(self.storage_dir).save(entry["kind"], entry["item"], entry["question"] or None)
                except ValueError as problem:
                    raise BadRequest(str(problem)) from None
                entry["saved"] = True
        return {"saved": True}

    def notebook_note(self, text):
        with self.state_lock:
            Notebook(self.storage_dir).add_note(text)
        return self.notebook_items()

    def notebook_delete(self, number):
        with self.state_lock:
            Notebook(self.storage_dir).delete(number)
        return self.notebook_items()

    def notebook_ask(self, question):
        return self.with_ai(lambda: card(Notebook(self.storage_dir).ask(question, self.chain), NOT_IN_NOTEBOOK))

    # --- Reading mode -------------------------------------------------------------------------
    def document(self, name):
        """The loaded document, or a clear problem."""
        if not self.ready.is_set():
            raise BadRequest(STILL_LOADING)
        if name not in {p.name for p in self.paths()}:
            raise BadRequest(CHOOSE_DOCUMENT)
        for document in self.searcher.library.documents:
            if document.name == name:
                return document
        raise BadRequest(FILE_BEING_CHECKED)

    def read_page(self, name, page):
        """One page's exact text. Uses no AI."""
        try:
            view = view_page(self.document(name), self.upload_dir / name, page)
        except BadRequest:
            raise
        except ValueError as problem:
            raise BadRequest(str(problem)) from None
        return {"doc": view.doc, "page": view.page, "total": view.total, "text": view.text, "previous": view.previous,
                "next": view.next, "warning": view.warning, "where": view.where}

    def ask_on_page(self, name, page, question):
        return self.with_ai(lambda: self.savable_card(
            "chat", ask_page(question, self.document(name), page, self.chain), question, NOT_ON_PAGE), name)

    # --- Book maker ---------------------------------------------------------------------------
    def make_book(self, name, topics):
        """One chapter per topic, with one AI call each. The book is saved if it has any fact."""
        def job():
            try:
                chapters = make_book(topics, self.searcher.for_document(name), self.chain)
            except ValueError as problem:
                return busy_card(str(problem))
            saved = ""
            if any(chapter.facts for chapter in chapters):
                saved = save_book(name, chapters, self.storage_dir).name
            return {"kind": "book", "saved": saved, "chapters": [chapter_view(c) for c in chapters]}
        return self.with_ai(job, name)

    # --- Research -----------------------------------------------------------------------------
    def research(self, question):
        """A web answer, never mixed with documents. It cannot be saved to the notebook."""
        return self.with_ai(lambda: card(research(question, self.chain, self.search_web), NOT_FOUND_WEB, "web", FROM_THE_WEB))


def chapter_view(chapter):
    """One chapter for the page: its facts, or the card that says why it has none."""
    facts = [{"question": fact.question, "card": card(fact)} for fact in chapter.facts]
    if facts:
        return {"topic": chapter.topic, "facts": facts}
    if chapter.status == REFUSED:
        return {"topic": chapter.topic, "facts": [], "card": refused_card(text=chapter.text if chapter.text != NOT_FOUND else "")}
    return {"topic": chapter.topic, "facts": [], "card": busy_card(chapter.text)}


def clean_file_name(name):
    """The bare file name, or "" if it could reach outside the folder or is not a normal name."""
    name = (name or "").strip()
    bare = Path(name.replace("\\", "/")).name
    if bare != name or bare in (".", "..") or any(ord(c) < 32 or c in '<>:"|?*' for c in bare):
        return ""
    return bare


def field_text(data, key):
    """A required piece of typed text from a request, within the size limit."""
    text = str(data[key]).strip()
    if not text or len(text) > MAX_QUESTION_CHARS:
        raise BadRequest(f"Please type at most {MAX_QUESTION_CHARS} characters.")
    return text


def field_topic(data):
    """An optional topic: empty means facts from across the document."""
    topic = str(data.get("topic") or "").strip()
    if len(topic) > MAX_QUESTION_CHARS:
        raise BadRequest(f"Please type at most {MAX_QUESTION_CHARS} characters.")
    return topic or None


def field_topics(data):
    return [t.strip() for t in re.split(r"[,\n]", field_text(data, "topics")) if t.strip()]


# What each POST address does. A missing or wrong field becomes a clear error (Handler.handle_call).
ROUTES = {
    "/api/ask": lambda app, d: app.ask(str(d["document"]), field_text(d, "question")),
    "/api/quiz": lambda app, d: app.quiz(str(d["document"]), field_topic(d)),
    "/api/quiz/answer": lambda app, d: app.quiz_answer(str(d["id"]), int(d["choice"])),
    "/api/flashcard": lambda app, d: app.flashcard(str(d["document"]), field_topic(d)),
    "/api/notebook/save": lambda app, d: app.notebook_save(str(d["id"])),
    "/api/notebook/note": lambda app, d: app.notebook_note(field_text(d, "text")),
    "/api/notebook/delete": lambda app, d: app.notebook_delete(int(d["id"])),
    "/api/notebook/ask": lambda app, d: app.notebook_ask(field_text(d, "question")),
    "/api/page": lambda app, d: app.read_page(str(d["document"]), int(d["page"])),
    "/api/page/ask": lambda app, d: app.ask_on_page(str(d["document"]), int(d["page"]), field_text(d, "question")),
    "/api/book": lambda app, d: app.make_book(str(d["document"]), field_topics(d)),
    "/api/research": lambda app, d: app.research(field_text(d, "question")),
}


class Handler(BaseHTTPRequestHandler):
    app = None
    server_version = "LearnBot"
    body_was_read = False
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

    def read_body(self, length):
        self.body_was_read = True
        return self.rfile.read(length)

    def read_a_little(self):
        """Closing with data still unread can lose the reply on Windows, so read some of it first."""
        if self.command == "POST" and not self.body_was_read:
            length = self.headers.get("Content-Length", "")
            if length.isdigit():
                self.read_body(min(int(length), MAX_UNREAD_BYTES))

    def send_problem(self, status, message):
        self.read_a_little()
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
        elif self.path == "/api/notebook":
            try:
                self.send_json(self.app.notebook_items())
            except (OSError, ValueError, KeyError):
                self.send_problem(500, WENT_WRONG)
        else:
            self.send_problem(404, "Not found.")

    def do_POST(self):
        if not self.host_is_ours() or not self.post_is_ours():
            self.send_problem(403, "Not allowed.")
            return
        url = urlparse(self.path)
        if url.path in ROUTES:
            self.handle_call(ROUTES[url.path])
        elif url.path == "/api/upload":
            self.handle_upload(parse_qs(url.query).get("name", [""])[0])
        else:
            self.send_problem(404, "Not found.")

    def handle_call(self, route):
        length = self.body_length(MAX_QUESTION_CHARS * 8)
        if length is None:
            return
        try:
            reply = route(self.app, json.loads(self.read_body(length).decode("utf-8")))
        except BadRequest as problem:
            self.send_problem(400, str(problem))
        except (ValueError, KeyError, TypeError, AttributeError):
            self.send_problem(400, "This request could not be read.")
        except Exception:  # noqa: BLE001 - the error's own text is never shown
            self.send_problem(500, WENT_WRONG)
        else:
            self.send_json(reply)

    def handle_upload(self, name):
        name = clean_file_name(name)
        if not name:
            self.send_problem(400, "This file name can't be used.")
            return
        length = self.body_length(config.MAX_FILE_MB * 1024 * 1024)
        if length is None:
            return
        self.app.add_upload(name, self.read_body(length))
        self.send_json({"accepted": name}, 202)


def make_server(app, port=0):
    """The server, listening on this laptop only. port 0: any free port."""
    handler = type("AppHandler", (Handler,), {"app": app})
    return ThreadingHTTPServer((HOST, port), handler)
