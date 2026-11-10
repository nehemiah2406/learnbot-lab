"""The LearnBot page: the real server and real pipeline, with a fake AI (no network beyond this laptop)."""

import http.client
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote as url_quote

import pytest
from test_quiz import FakeChain

from learnbot.answer import ANSWERED, Answer
from learnbot.index import Library
from learnbot.research import WebSearchFailed
from learnbot.search import Searcher
from learnbot.webapp import FROM_DOCUMENT, HOST, PAGE, App, card, clean_file_name, make_server

QUOTE = "The ladder rungs must be spaced 12 inches apart along the side rails."
COND = "Any boat 16 feet and longer (except canoes and kayaks) must also carry one throwable PFD (Type IV)."
TEXT = f"{QUOTE}\n\n{COND}\n\nEvery ladder needs a level base and a clear area around the bottom of it at all times.\n"
QUESTION = "How far apart must ladder rungs be spaced?"


def chat_reply(answer="12 inches apart", quote=QUOTE, page=1):
    return json.dumps({"found": True, "answer": answer, "sources": [{"doc": "guide.txt", "page": page, "quote": quote}]})


class Chain(FakeChain):
    providers = ("fake",)
    max_calls = None


def no_web(question):
    raise AssertionError("a test must never use the real web search")


class Site:
    def __init__(self, folder, chain):
        self.storage = folder / "storage"
        self.uploads = folder / "uploads"
        self.uploads.mkdir()

        def make_searcher(paths, previous=None):
            return Searcher(Library.load(paths, None, self.storage), "bm25")
        self.log_path = folder / "logs" / "selftest.log"
        self.app = App(self.uploads, self.storage, lambda: chain, make_searcher, log_dir=folder / "logs", search_web=no_web)
        self.app.start()
        self.server = make_server(self.app)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        assert self.app.ready.wait(10)

    def request(self, method, path, body=None, headers=None, host=None):
        connection = http.client.HTTPConnection(HOST, self.port, timeout=10)
        all_headers = {"Host": host or f"127.0.0.1:{self.port}", **(headers or {})}
        connection.request(method, path, body, all_headers)
        reply = connection.getresponse()
        data = reply.read()
        connection.close()
        return reply, data

    def post(self, path, body=b"", headers=None):
        reply, data = self.request("POST", path, body, {"X-LearnBot": "1", **(headers or {})})
        return reply.status, json.loads(data)

    def ask(self, question=QUESTION, document="guide.txt"):
        status, data = self.post("/api/ask", json.dumps({"document": document, "question": question}).encode("utf-8"))
        assert status == 200
        return data

    def status(self):
        return json.loads(self.request("GET", "/api/status")[1])

    def upload(self, name, content):
        return self.post(f"/api/upload?name={url_quote(name)}", content)

    def wait_until_idle(self):
        for _ in range(200):
            if not self.status()["working"]:
                return self.status()
            time.sleep(0.05)
        raise AssertionError("upload did not finish")


@pytest.fixture
def make_site(tmp_path):
    sites = []

    def make(*replies, fail=False, files=True):
        site = Site(tmp_path, Chain(*replies, fail=fail))
        if files:
            (site.uploads / "guide.txt").write_text(TEXT, encoding="utf-8")
            site.app.searcher = site.app.make_searcher(site.app.paths())
        sites.append(site)
        return site
    yield make
    for site in sites:
        site.server.shutdown()
        site.server.server_close()


# --- This laptop only -----------------------------------------------------------------
def test_server_listens_on_this_laptop_only(make_site):
    assert make_site().server.server_address[0] == "127.0.0.1"


@pytest.mark.parametrize("path", ["/", "/api/status"])
def test_look_alike_address_is_refused(make_site, path):
    site = make_site()
    assert site.request("GET", path, host="evil.example.com")[0].status == 403


def test_localhost_is_allowed(make_site):
    site = make_site()
    assert site.request("GET", "/", host=f"localhost:{site.port}")[0].status == 200


def test_another_web_site_cannot_post(make_site):
    site = make_site(chat_reply())
    body = json.dumps({"document": "guide.txt", "question": QUESTION})
    assert site.request("POST", "/api/ask", body, {"Origin": "https://evil.example.com", "X-LearnBot": "1"})[0].status == 403
    assert site.app.chain.prompts == []


def test_post_without_the_header_is_refused(make_site):
    site = make_site(chat_reply())
    body = json.dumps({"document": "guide.txt", "question": QUESTION})
    assert site.request("POST", "/api/ask", body, {"Content-Type": "text/plain"})[0].status == 403
    assert site.request("POST", "/api/upload?name=a.txt", b"x")[0].status == 403
    assert site.app.chain.prompts == [] and not (site.uploads / "a.txt").exists()


def test_own_origin_is_allowed(make_site):
    site = make_site(chat_reply())
    body = json.dumps({"document": "guide.txt", "question": QUESTION}).encode()
    status, _ = site.post("/api/ask", body, {"Origin": f"http://127.0.0.1:{site.port}"})
    assert status == 200


def test_unknown_address_is_not_found(make_site):
    site = make_site()
    assert site.request("GET", "/.env")[0].status == 404
    assert site.request("GET", "/../.env")[0].status == 404
    assert site.post("/api/nothing")[0] == 404


def test_every_reply_has_the_security_headers(make_site):
    reply, _ = make_site().request("GET", "/")
    assert "default-src 'none'" in reply.getheader("Content-Security-Policy")
    assert reply.getheader("X-Content-Type-Options") == "nosniff" and reply.getheader("X-Frame-Options") == "DENY"


# --- The page -------------------------------------------------------------------------
PAGE_TEXT = PAGE.read_text(encoding="utf-8")


def test_page_is_served(make_site):
    reply, data = make_site().request("GET", "/")
    assert reply.status == 200 and "text/html" in reply.getheader("Content-Type") and b"LearnBot" in data


def test_page_loads_nothing_from_outside():
    assert not re.findall(r"""(?:https?:)?//[a-z0-9]""", re.sub(r"//[^\n]*\n", "\n", PAGE_TEXT.replace("xmlns", "")).lower())
    assert "<link" not in PAGE_TEXT and "@import" not in PAGE_TEXT and "src=" not in PAGE_TEXT


def test_text_from_the_server_never_becomes_html():
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe not in PAGE_TEXT


@pytest.mark.parametrize("colour", ["#0F766E", "#F59E0B", "#F8FAFC", "#0F172A"])
def test_study_teal_colours_are_used(colour):
    assert colour in PAGE_TEXT


@pytest.mark.parametrize("text", ["DOCUMENTS", "+ Add documents", "MODE", "Chat", "Quiz", "Flashcards", "Notebook",
                                  "Reading mode", "Book maker", "Research", ">Web<", "Quiz score today", "Show quote", ">Ask<"])
def test_approved_layout_is_on_the_page(text):
    assert text in PAGE_TEXT


def test_header_has_only_the_icon_and_the_name():
    header = PAGE_TEXT.split('<header class="topbar">')[1].split("</header>")[0]
    assert "<svg" in header and re.sub(r"<svg.*?</svg>", "", header, flags=re.S).split() == ["<h1>LearnBot</h1>"]


def test_the_web_warning_line_is_not_on_the_page():
    assert "can be wrong" not in PAGE_TEXT


# --- Chat -----------------------------------------------------------------------------
def test_answer_card_has_green_label_location_text_and_show_quote(make_site):
    data = make_site(chat_reply()).ask()
    assert (data["kind"], data["label"], data["text"]) == ("document", FROM_DOCUMENT, "12 inches apart")
    assert data["showQuote"] is True
    assert data["sources"][0]["doc"] == "guide.txt" and data["sources"][0]["location"] == "Line 1"
    assert data["sources"][0]["quote"] == QUOTE


def test_show_quote_is_hidden_when_the_answer_is_the_sentence(make_site):
    assert make_site(chat_reply(answer=QUOTE)).ask()["showQuote"] is False


def test_show_quote_is_hidden_when_only_a_paragraph_number_differs():
    sources = [{"doc": "a.pdf", "page": 2, "quote": "(36) Squat denotes a change in trim."}]
    same = Answer(ANSWERED, "Squat denotes a change in trim.", [], sources=sources)
    other = Answer(ANSWERED, "A change in trim.", [], sources=sources)
    assert card(same)["showQuote"] is False and card(same)["sources"][0]["quote"].startswith("(36)")
    assert card(other)["showQuote"] is True


def test_dropped_condition_shows_the_sentence_and_no_button(make_site):
    site = make_site(chat_reply("One throwable PFD (Type IV).", COND, 2))
    data = site.ask("What must any boat 16 feet and longer also carry?")
    assert data["text"] == COND and data["showQuote"] is False


@pytest.mark.parametrize("reply", [
    '{"found": false}', "not json", chat_reply(answer="99 inches apart"), chat_reply(quote="The rungs are 99 inches apart."),
])
def test_anything_unproved_gets_the_red_label(make_site, reply):
    data = make_site(reply).ask()
    assert (data["kind"], data["label"], data["text"], data["sources"]) == ("refused", "Not in this document", "", [])


def test_question_with_no_word_in_the_document_asks_no_ai(make_site):
    site = make_site()
    assert site.ask("Xylophone zebra?")["kind"] == "refused" and site.app.chain.prompts == []


def test_answers_come_only_from_the_chosen_document(make_site):
    site = make_site('{"found": false}')
    (site.uploads / "other.txt").write_text("The ladder rungs in the other file are secret text here.", encoding="utf-8")
    site.app.searcher = site.app.make_searcher(site.app.paths())
    site.ask()
    assert QUOTE in site.app.chain.prompts[0] and "secret" not in site.app.chain.prompts[0]


def test_answer_from_another_document_is_refused(make_site):
    site = make_site(json.dumps({"found": True, "answer": "9 inches", "sources": [
        {"doc": "other.txt", "page": 1, "quote": "The rungs in the other file are 9 inches apart."}]}))
    (site.uploads / "other.txt").write_text("The rungs in the other file are 9 inches apart.", encoding="utf-8")
    site.app.searcher = site.app.make_searcher(site.app.paths())
    assert site.ask()["kind"] == "refused"


def test_busy_ai_is_a_friendly_message_without_pieces(make_site):
    data = make_site(fail=True).ask()
    assert data["kind"] == "busy" and "try again" in data["text"] and "pieces" not in data["text"] and not data["sources"]


def test_unknown_document_is_a_friendly_message(make_site):
    site = make_site(chat_reply())
    assert "choose a document" in site.ask(document="../../.env")["text"] and site.app.chain.prompts == []


def test_call_limit_is_a_friendly_message(make_site):
    site = make_site(fail="limit")
    assert "limit" in site.ask()["text"]


def test_error_text_is_never_shown(make_site):
    site = make_site(chat_reply())

    def broken(*args, **kwargs):
        raise RuntimeError("secret error text")
    site.app.chain.ask = broken
    data = site.ask()
    assert data["kind"] == "busy" and "secret" not in json.dumps(data)


def test_no_ai_key_is_a_friendly_message(make_site):
    site = make_site(chat_reply())
    site.app.chain.providers = ()
    assert "no AI key" in site.ask()["text"]


def test_question_while_a_file_is_checked_is_a_friendly_message(make_site):
    site = make_site(chat_reply())
    with site.app.ai_lock:
        assert "new file ready" in site.ask()["text"]
    assert site.app.chain.prompts == []


def test_question_before_the_models_load_is_a_friendly_message(make_site):
    site = make_site(chat_reply())
    site.app.ready.clear()
    assert "still starting" in site.ask()["text"]


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"document": "guide.txt"}',
                                  b'{"document": "guide.txt", "question": "  "}'])
def test_bad_question_is_a_clear_error(make_site, body):
    assert make_site().post("/api/ask", body)[0] == 400


def test_too_long_question_is_refused(make_site):
    site = make_site()
    body = json.dumps({"document": "guide.txt", "question": "word " * 300}).encode()
    assert site.post("/api/ask", body)[0] == 400


# --- Upload ---------------------------------------------------------------------------
def test_upload_shows_only_uploaded_and_the_self_test_result_is_only_in_the_log(make_site):
    site = make_site('{"found": false}', files=False)
    assert site.upload("guide.txt", TEXT.encode())[0] == 202
    status = site.wait_until_idle()
    assert (site.uploads / "guide.txt").read_text(encoding="utf-8") == TEXT
    assert status["documents"] == [{"name": "guide.txt", "badge": "Uploaded", "badgeKind": "good"}]
    assert status["notices"] == [] and "elf-test" not in json.dumps(status)
    assert "guide.txt | self-test warning: 0/5" in site.log_path.read_text(encoding="utf-8")


def test_self_check_warning_goes_to_the_log_not_the_page(make_site):
    site = make_site('{"found": false}', files=False)
    site.upload("short.txt", b"Only a few words in this small file.")
    status = site.wait_until_idle()
    assert status["documents"][0]["badge"] == "Uploaded" and status["notices"] == []
    assert "short.txt | self-check:" in site.log_path.read_text(encoding="utf-8")


def test_page_has_no_self_test_text_or_yellow_notice():
    assert "Self-test" not in PAGE_TEXT and ".notice.warn" not in PAGE_TEXT and "Ready" not in PAGE_TEXT


def test_file_being_added_shows_adding_then_uploaded(make_site):
    site = make_site(files=False)
    with site.app.ai_lock:
        site.upload("guide.txt", TEXT.encode())
        assert site.status()["documents"] == [{"name": "guide.txt", "badge": "Adding", "badgeKind": "busy"}]
    assert site.wait_until_idle()["documents"][0]["badge"] == "Uploaded"


def test_uploaded_file_can_be_asked_at_once(make_site):
    site = make_site('{"found": false}', files=False)
    site.upload("guide.txt", TEXT.encode())
    site.wait_until_idle()
    site.app.chain.replies = [chat_reply()]
    assert site.ask()["kind"] == "document"


def test_same_file_again_is_not_tested_again(make_site):
    site = make_site('{"found": false}', files=False)
    site.upload("guide.txt", TEXT.encode())
    site.wait_until_idle()
    prompts = len(site.app.chain.prompts)
    site.upload("guide.txt", TEXT.encode())
    site.wait_until_idle()
    assert len(site.app.chain.prompts) == prompts


@pytest.mark.parametrize("name, content, message", [
    ("virus.exe", b"MZ\x00\x00", "can't be read"), ("empty.txt", b"", "No text"),
    ("old.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "save it as"), ("photo.png", b"\x89PNG\r\n\x1a\n", "can't be read yet"),
])
def test_file_that_cannot_be_used_shows_why_and_is_not_added(make_site, name, content, message):
    site = make_site(files=False)
    site.upload(name, content)
    status = site.wait_until_idle()
    assert status["documents"] == [] and message in status["notices"][-1]["message"]
    assert status["notices"][-1]["kind"] == "error"


def test_different_file_with_the_same_name_is_not_overwritten(make_site):
    site = make_site()
    site.upload("guide.txt", b"Another file with the same name and enough words to be read as a file here.")
    status = site.wait_until_idle()
    assert "already uploaded" in status["notices"][-1]["message"]
    assert (site.uploads / "guide.txt").read_text(encoding="utf-8") == TEXT


@pytest.mark.parametrize("name", ["../evil.txt", "..\\evil.txt", "a/b.txt", "C:\\evil.txt", "..", "", "a?.txt", "a\nb.txt"])
def test_unsafe_file_name_is_refused(make_site, name):
    site = make_site()
    assert site.upload(name, b"text")[0] == 400
    assert not (site.uploads.parent / "evil.txt").exists() and [p.name for p in site.uploads.iterdir()] == ["guide.txt"]


def test_file_over_the_limit_is_refused_before_it_is_read(make_site, monkeypatch):
    monkeypatch.setattr("learnbot.config.MAX_FILE_MB", 0)
    site = make_site(files=False)
    status, data = site.upload("big.txt", b"x" * 100)
    assert status == 413 and "smaller" in data["error"] and site.status()["documents"] == []


def test_upload_that_fails_inside_shows_a_friendly_message(make_site, monkeypatch):
    site = make_site(files=False)

    def broken(*args):
        raise RuntimeError("secret error text")
    monkeypatch.setattr("learnbot.webapp.upload_file", broken)
    site.upload("guide.txt", TEXT.encode())
    status = site.wait_until_idle()
    assert "could not be added" in status["notices"][-1]["message"] and "secret" not in json.dumps(status)


def test_call_limit_during_the_self_test_keeps_the_file_and_only_logs(make_site):
    site = make_site(fail="limit", files=False)
    site.upload("guide.txt", TEXT.encode())
    status = site.wait_until_idle()
    assert status["notices"] == [] and status["documents"][0]["badge"] == "Uploaded"
    assert "self-test not finished" in site.log_path.read_text(encoding="utf-8")


def test_broken_self_test_keeps_the_file_and_logs_no_error_text(make_site, monkeypatch):
    def broken(*args):
        raise RuntimeError("secret error text")
    monkeypatch.setattr("learnbot.webapp.self_test_once", broken)
    site = make_site(files=False)
    site.upload("guide.txt", TEXT.encode())
    status = site.wait_until_idle()
    log = site.log_path.read_text(encoding="utf-8")
    assert status["notices"] == [] and "RuntimeError" in log and "secret" not in log


def test_temporary_upload_folder_is_removed(make_site, monkeypatch, tmp_path):
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(temp))
    site = make_site('{"found": false}', files=False)
    site.upload("guide.txt", TEXT.encode())
    site.wait_until_idle()
    assert list(temp.iterdir()) == []


# --- Modes: quiz ----------------------------------------------------------------------
def quiz_reply(question="How far apart must ladder rungs be spaced?", answer="12 inches apart",
               wrong=("8 inches apart", "20 inches apart", "30 inches apart"), quote=QUOTE):
    return json.dumps({"found": True, "question": question, "answer": answer, "wrong": list(wrong),
                       "source": {"doc": "guide.txt", "page": 1, "quote": quote}})


def study_reply(question=QUESTION, answer="12 inches apart", quote=QUOTE):
    return json.dumps({"found": True, "question": question, "answer": answer,
                       "source": {"doc": "guide.txt", "page": 1, "quote": quote}})


def call(site, path, **data):
    status, reply = site.post(path, json.dumps(data).encode("utf-8"))
    assert status == 200, reply
    return reply


def new_question(site, topic="ladder rungs"):
    return call(site, "/api/quiz", document="guide.txt", topic=topic)


def test_quiz_question_has_options_and_location_but_not_the_answer(make_site):
    data = new_question(make_site(quiz_reply()))
    assert data["kind"] == "quiz" and len(data["options"]) == 4 and "12 inches apart" in data["options"]
    assert data["sources"][0]["location"] == "Line 1"
    for hidden in ("correct", "text", "quote", "card"):
        assert hidden not in data and hidden not in data["sources"][0]


def test_quiz_answer_shows_the_card_and_counts_in_todays_score(make_site):
    site = make_site(quiz_reply())
    question = new_question(site)
    right = question["options"].index("12 inches apart")
    data = call(site, "/api/quiz/answer", id=question["id"], choice=right)
    assert data["right"] is True and data["correct"] == right and data["score"] == {"right": 1, "asked": 1}
    assert data["card"]["kind"] == "document" and data["card"]["sources"][0]["quote"] == QUOTE
    assert site.status()["quizScore"] == {"right": 1, "asked": 1}


def test_wrong_quiz_answer_counts_and_only_the_first_choice_counts(make_site):
    site = make_site(quiz_reply())
    question = new_question(site)
    right = question["options"].index("12 inches apart")
    wrong = (right + 1) % 4
    assert call(site, "/api/quiz/answer", id=question["id"], choice=wrong)["right"] is False
    again = call(site, "/api/quiz/answer", id=question["id"], choice=right)
    assert again["right"] is False and again["chosen"] == wrong and again["score"] == {"right": 0, "asked": 1}


def test_quiz_score_is_kept_after_a_restart_but_only_for_today(make_site):
    site = make_site(quiz_reply())
    question = new_question(site)
    call(site, "/api/quiz/answer", id=question["id"], choice=0)
    path = site.storage / "quiz_score.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**saved, "date": "2000-01-01"}), encoding="utf-8")
    assert site.status()["quizScore"] == {"right": 0, "asked": 0}


@pytest.mark.parametrize("choice", [-1, 4])
def test_quiz_answer_with_no_such_option_is_refused(make_site, choice):
    site = make_site(quiz_reply())
    question = new_question(site)
    assert site.post("/api/quiz/answer", json.dumps({"id": question["id"], "choice": choice}).encode())[0] == 400
    assert site.status()["quizScore"]["asked"] == 0


def test_quiz_answer_to_an_unknown_id_is_refused(make_site):
    assert make_site().post("/api/quiz/answer", b'{"id": "nothing", "choice": 0}')[0] == 400


def test_each_click_uses_the_next_piece_and_at_most_three_tries(make_site):
    site = make_site('{"found": false}')
    (site.uploads / "more.txt").write_text("\n\n".join(f"Paragraph {i} about ladder rungs has enough words to be used in a quiz here." for i in range(9)),
                                           encoding="utf-8")
    site.app.searcher = site.app.make_searcher(site.app.paths())
    first = call(site, "/api/quiz", document="more.txt", topic="ladder rungs")
    assert first["kind"] == "refused" and "could not make a quiz question" in first["text"]
    assert len(site.app.chain.prompts) == 3
    call(site, "/api/quiz", document="more.txt", topic="ladder rungs")
    assert len(site.app.chain.prompts) == 6 and site.app.chain.prompts[0] != site.app.chain.prompts[3]


def test_quiz_with_no_topic_uses_the_document(make_site):
    assert new_question(make_site(quiz_reply()), topic="")["kind"] == "quiz"


def test_quiz_topic_not_in_the_document_asks_no_ai(make_site):
    site = make_site()
    data = new_question(site, "xylophone zebra")
    assert (data["kind"], data["label"], data["text"]) == ("refused", "Not in this document", "") and site.app.chain.prompts == []


def test_unproved_quiz_question_is_never_shown(make_site):
    data = new_question(make_site(quiz_reply(answer="99 inches apart")))
    assert data["kind"] == "refused" and "options" not in data


def test_busy_ai_in_quiz_is_friendly_and_the_piece_is_tried_again(make_site):
    site = make_site(fail=True)
    assert new_question(site)["kind"] == "busy"
    assert site.app.used_pieces[("quiz", "guide.txt", "ladder rungs")] == 0


# --- Modes: flashcards ----------------------------------------------------------------
def test_flashcard_has_front_and_card(make_site):
    data = call(make_site(study_reply()), "/api/flashcard", document="guide.txt", topic="ladder rungs")
    assert data["kind"] == "flashcard" and data["front"] == QUESTION
    assert data["card"]["kind"] == "document" and data["card"]["text"] == "12 inches apart"
    assert data["card"]["sources"][0]["location"] == "Line 1" and data["card"]["showQuote"] is True


def test_flashcard_that_is_the_sentence_has_no_show_quote(make_site):
    data = call(make_site(study_reply(answer=QUOTE)), "/api/flashcard", document="guide.txt", topic="ladder rungs")
    assert data["card"]["showQuote"] is False


def test_chat_answer_with_words_not_in_the_quote_shows_the_sentence(make_site):
    data = make_site(chat_reply(answer="The ladder rungs sit 12 inches apart.")).ask()
    assert data["text"] == QUOTE and data["showQuote"] is False


TIDES = "NOAA Tide Predictions allows the generation of predicted tides for more than 3000 locations along the coastline."
TIDES_Q = "For how many locations can predicted tides be generated?"


def test_answer_that_drops_more_than_shows_the_sentence_in_every_mode(make_site):
    site = make_site()
    (site.uploads / "tides.txt").write_text(TIDES + "\n", encoding="utf-8")
    site.app.searcher = site.app.make_searcher(site.app.paths())
    chat = json.dumps({"found": True, "answer": "3000", "sources": [{"doc": "tides.txt", "page": 1, "quote": TIDES}]})
    card = json.dumps({"found": True, "question": TIDES_Q, "answer": "3000", "source": {"doc": "tides.txt", "page": 1, "quote": TIDES}})
    site.app.chain.replies = [chat]
    asked = site.ask(TIDES_Q, document="tides.txt")
    assert asked["text"] == TIDES and asked["showQuote"] is False
    assert call(site, "/api/page/ask", document="tides.txt", page=1, question=TIDES_Q)["text"] == TIDES
    call(site, "/api/notebook/save", id=asked["saveId"])
    assert call(site, "/api/notebook/ask", question=TIDES_Q)["text"] == TIDES
    site.app.chain.replies = [card]
    assert call(site, "/api/flashcard", document="tides.txt", topic="predicted tides")["card"]["text"] == TIDES


def test_flashcard_with_words_not_in_the_quote_shows_the_sentence(make_site):
    data = call(make_site(study_reply(answer="12 inches between each step")), "/api/flashcard", document="guide.txt", topic="ladder rungs")
    assert data["card"]["text"] == QUOTE and data["card"]["showQuote"] is False


def test_quiz_option_is_not_changed_by_the_exact_words_rule(make_site):
    data = new_question(make_site(quiz_reply(answer="12 inches between rungs")))
    assert data["kind"] == "quiz" and "12 inches between rungs" in data["options"]


def test_unproved_flashcard_is_never_shown(make_site):
    data = call(make_site(study_reply(answer="99 inches apart")), "/api/flashcard", document="guide.txt", topic="ladder rungs")
    assert data["kind"] == "refused" and "front" not in data


# --- Modes: notebook ------------------------------------------------------------------
def notebook(site):
    return json.loads(site.request("GET", "/api/notebook")[1])["items"]


def test_chat_answer_can_be_saved_once_with_its_proof(make_site):
    site = make_site(chat_reply())
    data = site.ask()
    assert call(site, "/api/notebook/save", id=data["saveId"]) == {"saved": True}
    call(site, "/api/notebook/save", id=data["saveId"])
    items = notebook(site)
    assert len(items) == 1 and items[0]["question"] == QUESTION and items[0]["card"]["text"] == "12 inches apart"
    assert items[0]["card"]["kind"] == "document" and items[0]["card"]["sources"][0]["location"] == "Line 1"


def test_quiz_and_flashcard_can_be_saved(make_site):
    site = make_site(quiz_reply())
    question = new_question(site)
    answered = call(site, "/api/quiz/answer", id=question["id"], choice=0)
    call(site, "/api/notebook/save", id=answered["card"]["saveId"])
    site.app.chain.replies = [study_reply()]
    card_data = call(site, "/api/flashcard", document="guide.txt", topic="ladder rungs")
    call(site, "/api/notebook/save", id=card_data["card"]["saveId"])
    assert [item["question"] for item in notebook(site)] == [QUESTION, "How far apart must ladder rungs be spaced?"]


def test_refusal_cannot_be_saved(make_site):
    assert "saveId" not in make_site('{"found": false}').ask()


def test_page_cannot_save_text_it_made_up(make_site):
    site = make_site()
    status, _ = site.post("/api/notebook/save", json.dumps({"id": "made-up", "text": "99 inches"}).encode())
    assert status == 400 and notebook(site) == []


def test_note_is_labelled_listed_deleted_and_never_used_in_answers(make_site):
    site = make_site('{"found": false}')
    items = call(site, "/api/notebook/note", text="Ladder rungs note: 99 inches")["items"]
    assert items[0]["card"]["label"] == "Your note" and items[0]["card"]["sources"] == []
    data = call(site, "/api/notebook/ask", question="How far apart are ladder rungs?")
    assert (data["kind"], data["label"]) == ("refused", "Not in your notebook") and site.app.chain.prompts == []
    assert call(site, "/api/notebook/delete", id=items[0]["id"]) == {"items": []}


def test_notebook_question_is_answered_from_saved_items_only(make_site):
    site = make_site(chat_reply())
    call(site, "/api/notebook/save", id=site.ask()["saveId"])
    site.app.chain.prompts.clear()
    data = call(site, "/api/notebook/ask", question=QUESTION)
    assert data["kind"] == "document" and data["sources"][0]["quote"] == QUOTE
    assert "level base" not in site.app.chain.prompts[0]


def test_empty_note_is_refused(make_site):
    assert make_site().post("/api/notebook/note", b'{"text": "  "}')[0] == 400


# --- Modes: reading -------------------------------------------------------------------
def test_reading_shows_the_exact_part_and_uses_no_ai(make_site):
    site = make_site()
    data = call(site, "/api/page", document="guide.txt", page=1)
    assert data["text"] == QUOTE and data["page"] == 1 and data["total"] == 3 and data["where"] == "Line 1"
    assert data["previous"] is None and data["next"] == 2 and site.app.chain.prompts == []


@pytest.mark.parametrize("document, page", [("guide.txt", 99), ("../.env", 1)])
def test_reading_a_bad_page_or_file_is_a_clear_error(make_site, document, page):
    status, data = make_site().post("/api/page", json.dumps({"document": document, "page": page}).encode())
    assert status == 400 and data["error"]


def test_page_question_uses_only_that_page_and_its_own_refusal(make_site):
    site = make_site('{"found": false}')
    data = call(site, "/api/page/ask", document="guide.txt", page=1, question=QUESTION)
    assert (data["kind"], data["label"]) == ("refused", "Not on this page")
    assert QUOTE in site.app.chain.prompts[0] and "level base" not in site.app.chain.prompts[0]


def test_page_question_answer_has_location_and_can_be_saved(make_site):
    site = make_site(chat_reply())
    data = call(site, "/api/page/ask", document="guide.txt", page=1, question=QUESTION)
    assert data["kind"] == "document" and data["sources"][0]["location"] == "Line 1" and data["saveId"]


# --- Modes: book maker ----------------------------------------------------------------
def book_reply(*answers):
    return json.dumps({"found": True, "facts": [{"question": QUESTION, "answer": a, "source": {"doc": "guide.txt", "page": 1, "quote": QUOTE}}
                                                for a in answers]})


def test_book_has_checked_facts_and_is_saved(make_site):
    site = make_site(book_reply("12 inches apart"))
    data = call(site, "/api/book", document="guide.txt", topics="ladder rungs")
    fact = data["chapters"][0]["facts"][0]
    assert data["kind"] == "book" and data["chapters"][0]["topic"] == "ladder rungs" and fact["question"] == QUESTION
    assert fact["card"]["text"] == "12 inches apart" and fact["card"]["sources"][0]["location"] == "Line 1"
    assert (site.storage / "books" / data["saved"]).is_file()


def test_book_topics_split_on_commas_and_a_missing_topic_says_so(make_site):
    site = make_site(book_reply("12 inches apart"))
    data = call(site, "/api/book", document="guide.txt", topics="ladder rungs, xylophone zebra")
    assert [c["topic"] for c in data["chapters"]] == ["ladder rungs", "xylophone zebra"]
    assert data["chapters"][1]["facts"] == [] and data["chapters"][1]["card"]["label"] == "Not in this document"
    assert len(site.app.chain.prompts) == 1


def test_book_with_no_facts_is_not_saved(make_site):
    site = make_site(book_reply("99 inches apart"))
    data = call(site, "/api/book", document="guide.txt", topics="ladder rungs")
    assert data["saved"] == "" and "could not make a fact" in data["chapters"][0]["card"]["text"]
    assert not (site.storage / "books").exists()


def test_too_many_book_topics_is_a_friendly_message(make_site):
    site = make_site()
    data = call(site, "/api/book", document="guide.txt", topics=",".join(f"topic {i}" for i in range(9)))
    assert data["kind"] == "busy" and "1 to 8" in data["text"] and site.app.chain.prompts == []


def test_busy_ai_in_a_book_chapter_is_friendly(make_site):
    data = call(make_site(fail=True), "/api/book", document="guide.txt", topics="ladder rungs")
    assert data["chapters"][0]["card"]["kind"] == "busy"


# --- Modes: research ------------------------------------------------------------------
WEB_URL = "https://example.gov/ladders"
WEB_TEXT = "The web page says ladder rungs must be spaced 12 inches apart on every ladder."


def web_site(make_site, reply, results=None):
    site = make_site(reply)
    site.app.search_web = lambda question: [{"url": WEB_URL, "title": "Ladders", "content": WEB_TEXT}] if results is None else results
    return site


def web_reply(answer="12 inches apart", quote=WEB_TEXT):
    return json.dumps({"found": True, "answer": answer, "sources": [{"doc": WEB_URL, "page": 1, "quote": quote}]})


def test_research_answer_has_the_orange_label_and_its_link(make_site):
    data = call(web_site(make_site, web_reply()), "/api/research", question=QUESTION)
    assert (data["kind"], data["label"], data["text"]) == ("web", "From the web", "12 inches apart")
    assert data["sources"][0]["link"] == WEB_URL and data["sources"][0]["location"] == "" and data["showQuote"] is True


def test_research_answer_cannot_be_saved_to_the_notebook(make_site):
    assert "saveId" not in call(web_site(make_site, web_reply()), "/api/research", question=QUESTION)


def test_research_that_is_not_found_has_its_own_refusal(make_site):
    data = call(web_site(make_site, '{"found": false}'), "/api/research", question=QUESTION)
    assert (data["kind"], data["label"]) == ("refused", "Not found on the web pages checked")


def test_research_never_sends_document_text(make_site):
    site = web_site(make_site, '{"found": false}')
    asked = []
    original = site.app.search_web
    site.app.search_web = lambda question: asked.append(question) or original(question)
    call(site, "/api/research", question=QUESTION)
    assert asked == [QUESTION] and QUOTE not in site.app.chain.prompts[0] and WEB_TEXT in site.app.chain.prompts[0]


def test_web_search_failure_is_friendly(make_site, monkeypatch):
    monkeypatch.setattr("learnbot.research.record_failure", lambda *args, **kwargs: None)  # not the real log
    site = make_site('{"found": false}')

    def broken(question):
        raise WebSearchFailed("timeout")
    site.app.search_web = broken
    data = call(site, "/api/research", question=QUESTION)
    assert data["kind"] == "busy" and "Web search is not available" in data["text"] and site.app.chain.prompts == []


def test_web_text_never_reaches_document_chat(make_site):
    site = web_site(make_site, web_reply())
    call(site, "/api/research", question=QUESTION)
    site.app.chain.replies = ['{"found": false}']
    site.app.chain.prompts.clear()
    site.ask()
    assert WEB_TEXT not in site.app.chain.prompts[0] and WEB_URL not in site.app.chain.prompts[0]


# --- Modes: on the page ---------------------------------------------------------------
def test_later_tags_are_gone_and_every_mode_can_be_chosen():
    assert "Later" not in PAGE_TEXT
    for mode in ("chat", "quiz", "flashcards", "notebook", "reading", "book", "research"):
        assert f'data-mode="{mode}"' in PAGE_TEXT


def test_web_links_open_safely():
    assert 'rel = "noopener noreferrer"' in PAGE_TEXT


def test_ai_job_while_another_runs_is_friendly_in_every_mode(make_site):
    site = make_site(quiz_reply())
    with site.app.ai_lock:
        for path, data in [("/api/quiz", {"document": "guide.txt"}), ("/api/flashcard", {"document": "guide.txt"}),
                           ("/api/book", {"document": "guide.txt", "topics": "ladder"}), ("/api/research", {"question": "a b"}),
                           ("/api/notebook/ask", {"question": "a b"}), ("/api/page/ask", {"document": "guide.txt", "page": 1, "question": "a b"})]:
            assert call(site, path, **data)["kind"] == "busy", path
    assert site.app.chain.prompts == []


@pytest.mark.parametrize("path", ["/api/quiz", "/api/flashcard", "/api/book", "/api/page", "/api/research", "/api/notebook/note",
                                  "/api/notebook/save", "/api/notebook/delete", "/api/notebook/ask", "/api/page/ask", "/api/quiz/answer"])
def test_every_mode_address_needs_the_header_and_a_good_request(make_site, path):
    site = make_site()
    assert site.request("POST", path, "{}")[0].status == 403
    assert site.post(path, b"not json")[0] == 400 and site.post(path, b"{}")[0] == 400


def test_a_broken_notebook_file_is_a_friendly_error_with_no_error_text(make_site):
    site = make_site()
    (site.storage).mkdir(exist_ok=True)
    (site.storage / "notebook.json").write_text("not json", encoding="utf-8")
    status, data = site.post("/api/notebook/note", b'{"text": "hello"}')
    assert status == 400 and "JSON" not in json.dumps(data) and "Expecting" not in json.dumps(data)


# --- Small parts ----------------------------------------------------------------------
@pytest.mark.parametrize("name, clean", [
    ("guide.pdf", "guide.pdf"), ("my guide (2).docx", "my guide (2).docx"), ("../a.txt", ""), ("a\\b.txt", ""), ("", ""),
    (".", ""), ("con:x", ""),
])
def test_clean_file_name(name, clean):
    assert clean_file_name(name) == clean


def test_card_keeps_every_source_of_a_comparison():
    sources = [{"doc": "a.pdf", "page": 1, "quote": "One quote here.", "title": "T"},
               {"doc": "a.pdf", "page": 2, "quote": "Two quote here.", "title": ""}]
    data = card(Answer(ANSWERED, "An answer", [], sources=sources))
    assert [s["location"] for s in data["sources"]] == ["p.1", "p.2"] and data["showQuote"] is True


def test_nothing_is_logged(make_site, capsys):
    make_site(chat_reply()).ask()
    captured = capsys.readouterr()
    assert QUESTION not in captured.err and QUESTION not in captured.out


def test_the_app_never_reads_the_key_file():
    source = Path("src/learnbot/webapp.py").read_text(encoding="utf-8") + PAGE_TEXT
    assert "API_KEY" not in source and ".env" not in source
