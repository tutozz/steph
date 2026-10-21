"""D4 : mode questions à outils en lecture seule, derrière `qa_tools` (désactivé par défaut).

Le modèle reçoit seulement la liste des commandes et lit l'historique par des outils. Invariant de
sécurité et de vie privée : un outil ne lit que ce que steph a déjà capturé dans CETTE session ;
jamais le système de fichiers, le réseau, l'exécution d'une commande ni une autre session.
"""

import ast
import builtins
import json
import os
import queue
import socket
import subprocess
import threading
from pathlib import Path

import pytest

from steph import qa_tools
from steph.config import Config
from steph.narrator import Narrator
from steph.qa_tools import TOOLS, SessionTools, ask_with_tools
from steph.server import ControlServer
from steph.session import Session

QA_TOOLS_SRC = Path(qa_tools.__file__)


def _session(cmds=None) -> Session:
    s = Session()
    s.cwd = "~/pricing"
    for cmd, out, code in cmds or [
        ("pytest -q", "..F..F\nFAILED tests/test_a.py::test_one\nFAILED tests/test_a.py::test_two\n2 failed, 4 passed\n", 1),
        ("ls", "a.py\nb.py\nnotes.txt\n", 0),
        ("pytest -q", "......\n6 passed\n", 0),
    ]:
        c = s.start(cmd)
        c.feed(out.encode())
        c.start, c.end, c.exit = 1000.0, 1002.0, code
    return s


# ------------------------------------------------------------------ outils
def test_tool_schemas_expose_exactly_the_four_read_only_tools():
    names = {t["function"]["name"] for t in TOOLS}
    assert names == {"search_history", "get_output", "command_info", "count_matches"}
    for t in TOOLS:
        assert t["type"] == "function"
        assert t["function"]["parameters"]["type"] == "object"


def test_index_lists_each_command_with_folder_code_duration_and_line_count_but_no_output():
    idx = SessionTools(_session()).index()
    lines = idx.splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("[1] ~/pricing $ pytest -q")
    assert "code 1" in lines[0] and "2 s" in lines[0] and "4 lignes" in lines[0]
    assert "FAILED" not in idx and "notes.txt" not in idx


def test_index_in_english():
    idx = SessionTools(_session(), language="en").index()
    assert "4 lines" in idx.splitlines()[0]


def test_index_says_when_nothing_ran_yet():
    assert SessionTools(Session()).index() == "(aucune commande exécutée pour l'instant)"


def test_search_history_returns_numbered_matching_lines_case_insensitive():
    out = SessionTools(_session()).call("search_history", {"pattern": "failed"})
    assert "[1] 2: FAILED tests/test_a.py::test_one" in out
    assert "[1] 4: 2 failed, 4 passed" in out
    assert "notes.txt" not in out


def test_search_history_can_be_limited_to_one_command():
    tools = SessionTools(_session())
    assert "6 passed" in tools.call("search_history", {"pattern": "passed", "command_id": 3})
    assert "4 passed" not in tools.call("search_history", {"pattern": "passed", "command_id": 3})


def test_search_history_treats_the_pattern_as_plain_text_not_a_regex():
    tools = SessionTools(_session([("echo", "a.b\naxb\n", 0)]))
    out = tools.call("search_history", {"pattern": "a.b"})
    assert "a.b" in out and "axb" not in out


def test_search_history_says_when_nothing_matches():
    assert SessionTools(_session()).call("search_history", {"pattern": "zzz"}) == "aucune ligne trouvée"


def test_get_output_returns_the_requested_window_with_line_numbers():
    out = SessionTools(_session()).call("get_output", {"command_id": 2, "start": 2, "count": 2})
    assert out == "2: b.py\n3: notes.txt"


def test_get_output_defaults_to_the_start_of_the_output():
    assert SessionTools(_session()).call("get_output", {"command_id": 2}).startswith("1: a.py")


def test_command_info_gives_folder_code_duration_and_lines():
    info = json.loads(SessionTools(_session()).call("command_info", {"command_id": 1}))
    assert info == {"id": 1, "command": "pytest -q", "folder": "~/pricing", "exit_code": 1,
                    "duration_s": 2, "lines": 4, "running": False}


def test_count_matches_counts_per_command():
    out = SessionTools(_session()).call("count_matches", {"pattern": "passed"})
    assert json.loads(out) == {"1": 1, "3": 1, "total": 2}
    assert json.loads(SessionTools(_session()).call("count_matches", {"pattern": "py", "command_id": 2})) == {"2": 2, "total": 2}


def test_unknown_command_id_is_an_error_message_not_an_exception():
    tools = SessionTools(_session())
    for args in ({"command_id": 0}, {"command_id": -1}, {"command_id": 99}, {"command_id": "x"}, {}):
        assert tools.call("command_info", args).startswith("erreur")


def test_results_are_capped_in_size():
    big = "\n".join(f"line {i} " + "x" * 60 for i in range(2000)) + "\n"
    tools = SessionTools(_session([("seq", big, 0)]), result_chars=500)
    for name, args in (("search_history", {"pattern": "line"}), ("get_output", {"command_id": 1, "count": 5000})):
        assert len(tools.call(name, args)) <= 500 + 60


# ------------------------------------------------------ invariant lecture seule
@pytest.mark.parametrize("name", ["read_file", "run_command", "shell", "open", "__init__", "_lines",
                                  "index", "call", "fetch", "list_sessions"])
def test_only_the_four_tools_can_be_called(name):
    assert SessionTools(_session()).call(name, {"path": "/etc/passwd", "command": "id"}).startswith("erreur")


def test_tools_never_touch_files_network_processes_or_another_session(tmp_path, monkeypatch):
    marker = "MARQUEUR-HORS-SESSION-4242"
    (tmp_path / "private.txt").write_text(marker)
    other = _session([("cat notes", marker + "\n", 0)])  # une autre fenêtre de steph
    tools = SessionTools(_session())

    def forbidden(*a, **k):
        raise AssertionError("un outil a tenté de sortir de la session")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr(os, "listdir", forbidden)
    monkeypatch.setattr(os, "scandir", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(os, "popen", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    hostile = [str(tmp_path / "private.txt"), "../private.txt", "/etc/passwd", marker, "*", "", "$(id)"]
    for pattern in hostile:
        for name in ("search_history", "count_matches"):
            assert marker not in tools.call(name, {"pattern": pattern})
            assert marker not in tools.call(name, {"pattern": pattern, "command_id": 1})
    for cid in (1, 2, 3, 4, 0, -1, "1; cat /etc/passwd", str(tmp_path / "private.txt")):
        for name in ("get_output", "command_info"):
            assert marker not in tools.call(name, {"command_id": cid, "start": -5, "count": 10 ** 9})
    assert marker not in tools.index()
    assert other.commands  # la donnée existe bien ailleurs, hors de portée


ALLOWED_IMPORTS = {"__future__", "json", "re", "time", "dataclasses", "typing", "collections.abc", "prompts", "session", "strings"}
FORBIDDEN_CALLS = {"open", "eval", "exec", "compile", "__import__", "getattr", "setattr", "globals", "locals",
                   "vars", "input", "breakpoint"}


def test_qa_tools_module_imports_nothing_that_can_reach_outside_the_session():
    tree = ast.parse(QA_TOOLS_SRC.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in ALLOWED_IMPORTS, alias.name
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module] if node.module else [alias.name for alias in node.names]
            for module in modules:
                assert module in ALLOWED_IMPORTS, module
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in FORBIDDEN_CALLS, node.func.id


# ------------------------------------------------------------ boucle d'appels
class ToolLLM:
    """Faux llama-server : rejoue une suite de réponses de /v1/chat/completions (message)."""

    def __init__(self, replies, delay=0.0):
        self.replies = list(replies)
        self.requests: list[dict] = []
        self.delay = delay

    def chat(self, messages, tools=None, **kw):
        import time
        self.requests.append({"messages": json.loads(json.dumps(messages)), "tools": tools, **kw})
        if self.delay:
            time.sleep(self.delay)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _call(name, args, cid="c1"):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def _cfg(**kw):
    cfg = Config()
    cfg.qa_tools = True
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def test_config_keeps_the_tool_mode_off_by_default():
    cfg = Config()
    assert cfg.qa_tools is False
    assert cfg.qa_tools_max_calls == 3


def test_first_request_carries_the_index_the_question_and_the_tools_but_no_output():
    llm = ToolLLM([_call("command_info", {"command_id": 1}), {"role": "assistant", "content": "Code 1."}])
    res = ask_with_tools(llm, _session(), "Combien d'échecs au premier pytest ?", _cfg())
    assert res.text == "Code 1." and res.calls == 1
    req = llm.requests[0]
    assert {t["function"]["name"] for t in req["tools"]} == {t["function"]["name"] for t in TOOLS}
    sent = json.dumps(req["messages"], ensure_ascii=False)
    assert "[1] ~/pricing $ pytest -q" in sent and "Combien d'échecs" in sent
    assert "FAILED" not in sent
    assert req["messages"][0]["role"] == "system"


def test_a_model_that_ignores_the_required_first_call_falls_back():
    # steph-speak v1.0 (Granite affiné, jamais entraîné aux outils) répond en texte libre au 1er tour
    llm = ToolLLM([{"role": "assistant", "content": "pytest ligne 1 échoue."}])
    assert ask_with_tools(llm, _session(), "q", _cfg()) is None


def test_tool_call_is_executed_and_its_result_sent_back_then_the_answer_is_returned():
    llm = ToolLLM([_call("search_history", {"pattern": "failed", "command_id": 1}),
                   {"role": "assistant", "content": "2 échecs."}])
    res = ask_with_tools(llm, _session(), "Combien d'échecs ?", _cfg())
    assert res.text == "2 échecs." and res.calls == 1
    second = llm.requests[1]["messages"]
    assert second[-2]["tool_calls"][0]["function"]["name"] == "search_history"
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "c1"
    assert "2 failed, 4 passed" in second[-1]["content"]
    assert "2 failed, 4 passed" in res.evidence  # ce que le modèle a vu, pour l'ancrage


def test_more_calls_than_the_cap_falls_back():
    llm = ToolLLM([_call("command_info", {"command_id": 1}, f"c{i}") for i in range(5)])
    assert ask_with_tools(llm, _session(), "q", _cfg(qa_tools_max_calls=3)) is None
    assert len(llm.requests) == 4  # 3 appels servis, le 4e demandé déclenche le repli


def test_deadline_exceeded_falls_back():
    llm = ToolLLM([_call("command_info", {"command_id": 1}), {"role": "assistant", "content": "x"}], delay=0.05)
    assert ask_with_tools(llm, _session(), "q", _cfg(qa_tools_timeout_seconds=0.01)) is None


def test_server_error_or_empty_answer_falls_back():
    assert ask_with_tools(ToolLLM([ConnectionError("HTTP 500")]), _session(), "q", _cfg()) is None
    empty = ToolLLM([_call("command_info", {"command_id": 1}), {"role": "assistant", "content": "  "}])
    assert ask_with_tools(empty, _session(), "q", _cfg()) is None


def test_malformed_tool_arguments_become_an_error_result_not_a_crash():
    bad = {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "get_output", "arguments": "{not json"}}]}
    llm = ToolLLM([bad, {"role": "assistant", "content": "Pas dans l'historique."}])
    res = ask_with_tools(llm, _session(), "q", _cfg())
    assert res.text == "Pas dans l'historique."
    assert llm.requests[1]["messages"][-1]["content"].startswith("erreur")


# ------------------------------------------------------------ chemin de production
class Speaker:
    def __init__(self):
        self.speaking = threading.Event()
        self._q: queue.Queue = queue.Queue()
        self.said: list[str] = []
        self._threads: list[threading.Thread] = []

    def say(self, text, interrupt=True, on_done=None, force=False):
        self.say_stream([text], interrupt, on_done, force)

    def say_stream(self, pieces, interrupt=True, on_done=None, force=False):
        th = threading.Thread(target=lambda: self.said.append("".join(pieces)), daemon=True)
        th.start()
        self._threads.append(th)

    def join(self):
        for th in self._threads:
            th.join(timeout=5)

    def stop(self):
        pass


class ServerLLM(ToolLLM):
    def __init__(self, replies, streamed="Réponse du mode actuel."):
        super().__init__(replies)
        self.streamed: list[list[dict]] = []
        self.answer = streamed
        self.active = 0
        self.last_done = 0.0

    def stream(self, messages, **kw):
        self.streamed.append(messages)
        yield self.answer

    def complete(self, messages, **kw):
        return ""

    def healthy(self):
        return True


def _ask(cfg, llm, question="Combien d'échecs au premier pytest ?"):
    sp = Speaker()
    nar = Narrator(cfg, _session(), sp, llm)
    nar.llm_ready = True
    srv = ControlServer.__new__(ControlServer)
    srv.nar = nar
    sent: list[str] = []
    srv._ask(question, lambda o: sent.append(o.get("t", "")) or True, speak=True)
    sp.join()
    return "".join(sent), nar, llm


def test_default_config_never_uses_the_tool_mode():
    llm = ServerLLM([])
    out, _, _ = _ask(Config(), llm)
    assert llm.requests == [] and len(llm.streamed) == 1
    assert out == "Réponse du mode actuel."


def test_tool_mode_answers_through_the_tools_and_grounds_on_what_the_model_saw():
    llm = ServerLLM([_call("search_history", {"pattern": "failed", "command_id": 1}),
                     {"role": "assistant", "content": "2 échecs, test_one et test_two."}])
    out, nar, _ = _ask(_cfg(), llm)
    assert out == "2 échecs, test_one et test_two."
    assert llm.streamed == []
    assert nar.s.qa[-1]["a"] == out


def test_tool_mode_cuts_a_fact_the_model_never_saw():
    llm = ServerLLM([_call("command_info", {"command_id": 2}),
                     {"role": "assistant", "content": "7 échecs."}])  # 7 ni dans la liste ni dans le résultat
    out, _, _ = _ask(_cfg(), llm)
    assert llm.streamed == [] and len(llm.requests) == 2
    assert "7" not in out


def test_tool_mode_falls_back_to_the_current_mode_when_the_cap_is_hit():
    llm = ServerLLM([_call("command_info", {"command_id": 1}, f"c{i}") for i in range(5)])
    out, nar, _ = _ask(_cfg(qa_tools_max_calls=2), llm)
    assert len(llm.requests) == 3
    assert len(llm.streamed) == 1 and out == "Réponse du mode actuel."
    assert llm.streamed[0][1]["content"].startswith("Historique de la session")


# ------------------------------------------------------------ client llama-server
def test_llm_chat_posts_the_tools_without_streaming_and_returns_the_message(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from steph import llm as llm_mod

    seen: list[dict] = []
    reply = {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
        {"id": "x", "type": "function", "function": {"name": "command_info", "arguments": "{\"command_id\": 1}"}}]}}]}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append({"path": self.path, "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.handle_request, daemon=True).start()
    monkeypatch.setattr(llm_mod, "RUNTIME_DIR", tmp_path)
    cfg = Config()
    cfg.llm_port = httpd.server_address[1]
    client = llm_mod.LLM(cfg)
    client.activity_file = tmp_path / "activity"
    client.busy_dir = tmp_path / "busy"
    msg = client.chat([{"role": "user", "content": "q"}], tools=TOOLS, max_tokens=50, slot=1, tool_choice="required")
    httpd.server_close()
    assert msg["tool_calls"][0]["function"]["name"] == "command_info"
    body = seen[0]["body"]
    assert seen[0]["path"] == "/v1/chat/completions"
    assert body["stream"] is False and body["tools"] == TOOLS and body["id_slot"] == 1
    assert body["max_tokens"] == 50 and body["tool_choice"] == "required"
    assert client.active == 0 and not any(client.busy_dir.iterdir())


# ------------------------------------------------ réglages mesurés sur Gemma 4 E2B (banc v3 dev)
def test_get_output_widens_a_window_too_small_to_hold_an_answer():
    big = "\n".join(f"line {i}" for i in range(1, 60)) + "\n"
    out = SessionTools(_session([("seq", big, 0)])).call("get_output", {"command_id": 1, "start": 1, "count": 1})
    assert out.splitlines()[0] == "1: line 1" and out.splitlines()[-1] == "59: line 59"


def test_get_output_too_long_keeps_the_head_and_the_tail_where_summaries_live():
    big = "".join(f"compiling module {i}\n" for i in range(1, 400)) + "2 failed, 7 passed in 0.01s\n"
    out = SessionTools(_session([("make", big, 1)]), result_chars=800).call("get_output", {"command_id": 1})
    assert out.startswith("1: compiling module 1\n")
    assert out.endswith("400: 2 failed, 7 passed in 0.01s")
    assert len(out) <= 800 + 60


def test_system_prompt_leaves_out_style_and_absence_rules_that_stop_tool_calls():
    from steph import prompts
    for system in (prompts.QA_TOOLS_SYSTEM, prompts.QA_TOOLS_SYSTEM_EN):
        assert "historique." not in system and "history." not in system and "25" not in system


def test_each_tool_result_ends_with_the_answer_rules_kept_out_of_the_evidence():
    from steph import prompts
    llm = ToolLLM([_call("get_output", {"command_id": 2}), {"role": "assistant", "content": "3 fichiers."}])
    res = ask_with_tools(llm, _session(), "Combien de fichiers ?", _cfg())
    tool_msg = llm.requests[1]["messages"][-1]
    assert tool_msg["content"].endswith(prompts.QA_TOOLS_ANSWER)
    assert "notes.txt" in tool_msg["content"]
    assert prompts.QA_TOOLS_ANSWER not in res.evidence and "notes.txt" in res.evidence


def test_english_tool_results_carry_the_english_answer_rules():
    from steph import prompts
    llm = ToolLLM([_call("get_output", {"command_id": 2}), {"role": "assistant", "content": "3 files."}])
    ask_with_tools(llm, _session(), "How many files?", _cfg(language="en"))
    assert llm.requests[1]["messages"][-1]["content"].endswith(prompts.QA_TOOLS_ANSWER_EN)


def test_first_round_must_call_a_tool_later_rounds_may_answer():
    llm = ToolLLM([_call("get_output", {"command_id": 2}), {"role": "assistant", "content": "3 fichiers."}])
    ask_with_tools(llm, _session(), "Combien de fichiers ?", _cfg())
    assert llm.requests[0].get("tool_choice") == "required"
    assert llm.requests[1].get("tool_choice") in (None, "auto")


def test_tool_mode_skips_the_history_warm_that_it_would_never_read():
    # le préchauffage P20 lit tout l'historique (jusqu'à 100 s de CPU sur l'i5 avec Gemma) pour rien
    for enabled, expected in ((False, 1), (True, 0)):
        llm = ServerLLM([])
        llm.completed = []
        llm.complete = lambda messages, **kw: llm.completed.append(messages) or ""
        nar = Narrator(_cfg(qa_tools=enabled), _session(), Speaker(), llm)
        nar.llm_ready = True
        nar._warm_pending = True
        nar._maybe_warm()
        deadline = __import__("time").time() + 2
        while nar._warming and __import__("time").time() < deadline:
            pass
        assert len(llm.completed) == expected


def test_line_numbers_added_by_the_tools_do_not_ground_a_count():
    # D4, défaut trouvé au juge : « 22 lignes ERROR » passait l'ancrage grâce au préfixe « 22: »
    out = "\n".join(f"step {chr(97 + i % 26)}" for i in range(30)) + "\n"
    llm = ServerLLM([_call("get_output", {"command_id": 1}), {"role": "assistant", "content": "22 erreurs."}])
    s = _session([("make", out, 2)])
    sp = Speaker()
    nar = Narrator(_cfg(), s, sp, llm)
    nar.llm_ready = True
    srv = ControlServer.__new__(ControlServer)
    srv.nar = nar
    sent: list[str] = []
    srv._ask("Combien d'erreurs ?", lambda o: sent.append(o.get("t", "")) or True, speak=False)
    assert "22" not in "".join(sent)
