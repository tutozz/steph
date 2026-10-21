"""Fenêtre au premier plan (Q2a) : sonde du système (macOS : Terminal, iTerm2) et repli
sur la dernière fenêtre où l'on a tapé."""

import subprocess
import time

import pytest

from steph import focus as focus_mod
from steph.focus import Focus, frontmost_tty, parse_front_app


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_parse_front_app_reads_the_display_name():
    out = '"iTerm2" ASN:0x0-0xd00d: (in front) \n    bundleID=[ NULL ] \n'
    assert parse_front_app(out) == "iTerm2"


def test_parse_front_app_without_name_is_none():
    assert parse_front_app("") is None


def fake_run(front_name: str, tty: str, calls: list):
    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["lsappinfo", "front"]:
            out = "ASN:0x0-0x1:\n"
        elif cmd[:2] == ["lsappinfo", "info"]:
            out = f'"{front_name}" ASN:0x0-0x1: (in front) \n'
        else:
            out = tty + "\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
    return run


@pytest.mark.parametrize("app", ["Terminal", "iTerm2"])
def test_frontmost_tty_asks_the_front_terminal(monkeypatch, app):
    monkeypatch.setattr(focus_mod.sys, "platform", "darwin")
    calls: list = []
    assert frontmost_tty(run=fake_run(app, "/dev/ttys004", calls)) == "/dev/ttys004"
    script = calls[-1][-1]
    assert calls[-1][0] == "osascript" and f'application "{app}"' in script


def test_frontmost_tty_never_scripts_a_non_terminal_app(monkeypatch):
    # AppleScript vers une application fermée la lancerait : on ne parle qu'au terminal déjà au premier plan
    monkeypatch.setattr(focus_mod.sys, "platform", "darwin")
    calls: list = []
    assert frontmost_tty(run=fake_run("Safari", "", calls)) is None
    assert not any(c[0] == "osascript" for c in calls)


def test_frontmost_tty_is_none_outside_macos(monkeypatch):
    monkeypatch.setattr(focus_mod.sys, "platform", "linux")
    calls: list = []
    assert frontmost_tty(run=fake_run("iTerm2", "/dev/ttys004", calls)) is None
    assert calls == []


def test_frontmost_tty_survives_a_failing_probe(monkeypatch):
    monkeypatch.setattr(focus_mod.sys, "platform", "darwin")

    def run(cmd, **kw):
        raise OSError("no lsappinfo")

    assert frontmost_tty(run=run) is None


def test_last_typed_window_is_foreground_without_probe():
    f = Focus(probe=lambda: None)
    f.note_input("a")
    f.note_input("b")
    assert f.foreground({"a": "/dev/ttys1", "b": "/dev/ttys2"}) == "b"


def test_nothing_known_means_no_foreground():
    f = Focus(probe=lambda: None)
    assert f.foreground({"a": "/dev/ttys1"}) is None


def test_probe_match_wins_over_older_typing():
    clock = Clock()
    f = Focus(probe=lambda: "/dev/ttys1", clock=clock)
    f.note_input("b")
    clock.now += 1
    f.refresh(wait=True)
    assert f.foreground({"a": "/dev/ttys1", "b": "/dev/ttys2"}) == "a"


def test_newer_typing_wins_over_older_probe():
    clock = Clock()
    f = Focus(probe=lambda: "/dev/ttys1", clock=clock)
    f.refresh(wait=True)
    clock.now += 1
    f.note_input("b")
    assert f.foreground({"a": "/dev/ttys1", "b": "/dev/ttys2"}) == "b"


def test_probe_on_an_unknown_tab_falls_back_to_typing():
    clock = Clock()
    f = Focus(probe=lambda: "/dev/ttys9", clock=clock)
    f.note_input("b")
    clock.now += 1
    f.refresh(wait=True)
    assert f.foreground({"a": "/dev/ttys1", "b": "/dev/ttys2"}) == "b"


def test_forgotten_window_is_never_foreground():
    f = Focus(probe=lambda: None)
    f.note_input("a")
    f.forget("a")
    assert f.foreground({"b": "/dev/ttys2"}) is None


def test_refresh_is_rate_limited():
    clock = Clock()
    calls = []
    f = Focus(probe=lambda: calls.append(1), clock=clock, min_interval=0.5)
    f.refresh(wait=True)
    f.refresh(wait=True)
    assert len(calls) == 1
    clock.now += 0.6
    f.refresh(wait=True)
    assert len(calls) == 2


def test_refresh_does_not_block_the_caller():
    f = Focus(probe=lambda: time.sleep(0.3) or "/dev/ttys1")
    t0 = time.monotonic()
    f.refresh()
    assert time.monotonic() - t0 < 0.1
