import time

import pytest

from steph import config as config_mod
from steph.config import Config, load_config
from steph.narrator import Narrator
from steph.session import Session


class FakeSpeaker:
    def __init__(self):
        self.said: list[str] = []
        self.speaking = type("E", (), {"is_set": staticmethod(lambda: False)})()
        self._q = type("Q", (), {"empty": staticmethod(lambda: True)})()

    def say(self, text, interrupt=True, on_done=None, force=False):
        self.said.append(text)

    def say_stream(self, pieces, interrupt=True, on_done=None, force=False):
        self.said.append("".join(pieces))

    def stop(self):
        pass

    def stop_all(self):
        pass

    def note_input(self):
        pass

    def repeat(self):
        pass


class FakeLLM:
    active = False
    last_done = 0.0

    def healthy(self):
        return True

    def stream(self, msgs, **kw):
        yield "résumé LLM"

    def complete(self, msgs, **kw):
        return "description"


def make(rules=None, logs=None, monkeypatch=None, **cfg_kw):
    cfg = Config(rules=rules or {}, **cfg_kw)
    if logs is not None:
        monkeypatch.setattr(Narrator, "_log", lambda self, msg: logs.append(msg))
    nar = Narrator(cfg, Session(), FakeSpeaker(), FakeLLM())
    nar.llm_ready = True
    return nar


def run_cmd(nar, cmd, output="", code=0, duration=0.1):
    nar.on_command_start(cmd)
    c = nar.s.current
    nar._handle(nar.events.get_nowait())
    c.start = time.time() - duration
    if output:
        c.feed(output.encode())
    nar._tick()
    nar.on_command_end(code, "/tmp")
    nar._handle(nar.events.get_nowait())
    return nar.sp.said


LONG = "\n".join(f"ligne numéro {i} avec quelques mots" for i in range(12)) + "\n"


def test_config_loads_rules_table(tmp_path, monkeypatch):
    p = tmp_path / "config.toml"
    p.write_text('[rules]\nwatch = "mute"\n"cat" = "verbatim"\n')
    monkeypatch.setattr(config_mod, "CONFIG_PATH", p)
    cfg = load_config()
    assert cfg.rules == {"watch": "mute", "cat": "verbatim"}


def test_default_rules_empty():
    assert Config().rules == {}


def test_mute_says_nothing_on_success():
    nar = make({"echo": "mute"})
    assert run_cmd(nar, "echo bonjour", "bonjour\n") == []


def test_mute_uses_first_word_after_sudo():
    nar = make({"watch": "mute"})
    assert run_cmd(nar, "sudo watch -n1 date", LONG, duration=30) == []


def test_mute_silences_running_updates():
    nar = make({"sleep": "mute"}, first_update_after=0.0)
    assert run_cmd(nar, "sleep 30", duration=30) == []


def test_mute_still_announces_errors():
    nar = make({"cat": "mute"})
    said = run_cmd(nar, "cat /nope", "cat: /nope: Aucun fichier ou dossier de ce type\n", code=1)
    assert said and "Aucun fichier" in said[-1]


def test_mute_all_silences_errors_too():
    nar = make({"cat": "mute-all"})
    assert run_cmd(nar, "cat /nope", "cat: /nope: Aucun fichier\n", code=1) == []


def test_verbatim_reads_long_output_in_full():
    nar = make({"cat": "verbatim"})
    said = run_cmd(nar, "cat f.txt", LONG)
    assert len(said) == 1
    assert "ligne numéro 0" in said[0] and "ligne numéro 11" in said[0]
    assert "résumé LLM" not in said[0]


def test_summary_forces_llm_on_short_output():
    nar = make({"make": "summary"})
    said = run_cmd(nar, "make", "ok\n")
    # le statut dit en code avant le premier jeton (P9) précède le résumé
    assert len(said) == 1 and said[0].endswith("résumé LLM.")


def test_no_rule_keeps_default_behaviour():
    nar = make({"make": "summary"})
    assert run_cmd(nar, "echo bonjour", "bonjour\n") == ["bonjour"]


def test_unknown_value_ignored_with_warning(monkeypatch):
    logs: list[str] = []
    nar = make({"echo": "chut"}, logs=logs, monkeypatch=monkeypatch)
    assert run_cmd(nar, "echo bonjour", "bonjour\n") == ["bonjour"]
    assert any("echo" in m and "chut" in m for m in logs)


def test_rules_not_a_table_is_ignored(monkeypatch):
    logs: list[str] = []
    nar = make("mute", logs=logs, monkeypatch=monkeypatch)
    assert run_cmd(nar, "echo bonjour", "bonjour\n") == ["bonjour"]
    assert any("rules" in m for m in logs)
