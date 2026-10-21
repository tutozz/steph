from steph import cli
from steph.config import Config
from steph.narrator import Narrator
from steph.proxy import PtyProxy
from steph.session import Session

from test_rules import FakeLLM, FakeSpeaker


def make():
    nar = Narrator(Config(), Session(), FakeSpeaker(), FakeLLM())
    nar.llm_ready = True
    return nar


def run(nar, cmd, output):
    nar.on_command_start(cmd)
    nar._handle(nar.events.get_nowait())
    nar.s.current.feed(output.encode())
    nar.on_command_end(0, "/tmp")
    nar._handle(nar.events.get_nowait())
    nar.sp.said.clear()


def press(nar, *keys):
    for k in keys:
        nar.on_key(k)
        nar._handle(nar.events.get_nowait())
    return nar.sp.said


THREE = "un\n\ndeux\n\x1b[31mtrois\x1b[0m\n"


def test_next_starts_at_first_line_and_skips_blank_lines():
    nar = make()
    run(nar, "ls", THREE)
    assert press(nar, "next", "next", "next") == ["un", "deux", "trois"]


def test_prev_starts_at_last_line():
    nar = make()
    run(nar, "ls", THREE)
    assert press(nar, "prev", "prev") == ["trois", "deux"]


def test_first_and_last():
    nar = make()
    run(nar, "ls", THREE)
    assert press(nar, "last", "first") == ["trois", "un"]


def test_bounds_announce_start_and_end():
    nar = make()
    run(nar, "ls", THREE)
    assert press(nar, "first", "prev") == ["un", "Début."]
    nar.sp.said.clear()
    assert press(nar, "last", "next") == ["trois", "Fin."]


def test_new_command_resets_cursor():
    nar = make()
    run(nar, "ls", THREE)
    press(nar, "next", "next")
    nar.sp.said.clear()
    run(nar, "echo a", "alpha\nbeta\n")
    assert press(nar, "next") == ["alpha"]


def test_running_command_reads_last_finished_and_resets_cursor():
    nar = make()
    run(nar, "ls", THREE)
    press(nar, "next", "next")
    nar.sp.said.clear()
    nar.on_command_start("sleep 30")
    nar._handle(nar.events.get_nowait())
    nar.s.current.feed(b"en cours\n")
    assert press(nar, "next") == ["un"]


def test_silent_commands_are_skipped():
    nar = make()
    run(nar, "ls", THREE)
    run(nar, "clear", "")
    assert press(nar, "first") == ["un"]


def test_no_command_yet():
    nar = make()
    assert press(nar, "next") == ["Aucune commande pour l'instant."]


def test_command_without_output():
    nar = make()
    run(nar, "true", "")
    assert press(nar, "next") == ["Aucune sortie."]


def test_default_keys_do_not_clash():
    cfg = Config()
    review = [cfg.key_line_first, cfg.key_line_prev, cfg.key_line_next, cfg.key_line_last]
    existing = [cfg.key_ask, cfg.key_stop, cfg.key_repeat, cfg.key_details]
    assert len(set(review)) == 4
    for k in review:
        assert all(k not in e and e not in k for e in existing)


def test_proxy_routes_review_keys_to_narrator():
    cfg = Config()
    got = []
    nar = type("N", (), {"on_key": lambda self, w: got.append(w),
                         "s": type("S", (), {"current": None})()})()
    proxy = PtyProxy(cfg, nar, "/tmp/unused.sock")
    data = (b"a" + cfg.key_line_first.encode() + cfg.key_line_prev.encode()
            + cfg.key_line_next.encode() + cfg.key_line_last.encode())
    assert proxy._on_input(data) == b"a"
    assert sorted(got) == sorted(["first", "prev", "next", "last"])


def test_ctl_sends_review_ops(monkeypatch):
    sent = []
    monkeypatch.setattr(cli, "find_socket", lambda _: "/tmp/sock")
    monkeypatch.setattr(cli, "request", lambda path, req, **kw: sent.append(req) or "")
    for op in ("prev", "next", "first", "last"):
        assert cli.main(["ctl", op]) == 0
    assert sent == [{"op": "prev"}, {"op": "next"}, {"op": "first"}, {"op": "last"}]


def test_control_server_forwards_review_ops():
    import io
    import json

    from steph.server import ControlServer

    got = []
    srv = ControlServer.__new__(ControlServer)
    srv.nar = type("N", (), {"on_key": lambda self, w: got.append(w)})()

    class Conn:
        def __init__(self, op):
            self.f = io.BytesIO((json.dumps({"op": op}) + "\n").encode())

        def makefile(self, *a, **kw):
            return self.f

        def close(self):
            pass

    for op in ("prev", "next", "first", "last"):
        srv._serve(Conn(op))
    assert got == ["prev", "next", "first", "last"]
