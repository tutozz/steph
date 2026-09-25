import argparse

from steph import cli


def run_ask(monkeypatch, typed: str, question: list[str]):
    sent = []
    monkeypatch.setattr(cli, "find_socket", lambda _: "/tmp/sock")
    monkeypatch.setattr(cli, "request", lambda path, req, **kw: sent.append(req) or "")
    monkeypatch.setattr("builtins.input", lambda prompt="": typed)
    args = argparse.Namespace(socket=None, mute=False, once=True, question=question)
    assert cli.cmd_ask(args) == 0
    return sent


def test_bare_q_prompts_once_and_keeps_apostrophes(monkeypatch):
    sent = run_ask(monkeypatch, "pourquoi l'install a planté ? \"vraiment\"", [])
    assert sent == [{"op": "ask", "q": "pourquoi l'install a planté ? \"vraiment\"", "speak": True}]


def test_bare_q_with_empty_line_asks_nothing(monkeypatch):
    assert run_ask(monkeypatch, "", []) == []


def test_q_with_words_does_not_prompt(monkeypatch):
    sent = run_ask(monkeypatch, "ne doit pas être lu", ["pourquoi", "?"])
    assert sent == [{"op": "ask", "q": "pourquoi ?", "speak": True}]
