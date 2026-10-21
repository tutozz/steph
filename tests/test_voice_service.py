"""Q2a : une seule voix partagée entre fenêtres. File d'attente, priorité à la fenêtre au
premier plan, annonces des autres préfixées par leur nom ; service lancé à la demande,
unique, arrêté avec la dernière fenêtre, relancé s'il meurt."""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from steph.config import DATA_DIR, Config
from steph.focus import Focus
from steph.voice_client import VoiceClient
from steph.voice_service import Scheduler, VoiceService, acquire_lock, window_label

REAL_VOICE = DATA_DIR / "voices" / "fr_FR-siwis-medium.onnx"


# ---------------------------------------------------------------- ordonnanceur

class Cuts:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1


def make_sched(n: int = 2):
    focus = Focus(probe=lambda: None)
    cuts = Cuts()
    s = Scheduler(focus, on_cut=cuts)
    wins, evs = [], []
    for i in range(n):
        ev: list = []
        evs.append(ev)
        wins.append(s.add_window(tty=f"/dev/ttys00{i}", pid=100 + i, send=ev.append))
    return s, focus, wins, evs, cuts


def submit(s, w, jid, *segs, close=True, lang="fr"):
    s.submit(w, jid, voice="v.onnx", rate=1.0, lang=lang)
    for t in segs:
        s.segment(w, jid, t)
    if close:
        s.end(w, jid)


def order(s) -> list:
    out = []
    while True:
        job = s.next_job(timeout=0.01)
        if job is None:
            return out
        out.append((job.window.n, job.id))
        s.finish(job)


def test_windows_get_short_stable_numbers():
    s, _, wins, _, _ = make_sched(3)
    assert [w.n for w in wins] == [1, 2, 3]
    s.remove_window(wins[1])
    assert s.add_window(tty="/dev/ttys9", pid=9, send=lambda ev: None).n == 2
    assert s.add_window(tty="/dev/ttys8", pid=8, send=lambda ev: None, want=7).n == 7


def test_window_label_in_both_languages():
    assert window_label("fr", 2) == "Fenêtre 2 :"
    assert window_label("en", 2) == "Window 2:"


def test_single_window_is_never_prefixed():
    s, _, wins, _, _ = make_sched(1)
    submit(s, wins[0], 1, "Succès.")
    job = s.next_job(timeout=0.1)
    assert s.prefix(job) is None


def test_background_window_is_prefixed_foreground_is_not():
    s, focus, (a, b), _, _ = make_sched(2)
    focus.note_input(a)
    submit(s, b, 1, "Succès.")
    submit(s, a, 2, "OK.")
    jobs = {}
    for _ in range(2):
        job = s.next_job(timeout=0.1)
        jobs[job.window.n] = s.prefix(job)
        s.finish(job)
    assert jobs == {1: None, 2: "Fenêtre 2 :"}


def test_prefix_follows_the_window_language():
    s, focus, (a, b), _, _ = make_sched(2)
    focus.note_input(a)
    submit(s, b, 1, "Success.", lang="en")
    assert s.prefix(s.next_job(timeout=0.1)) == "Window 2:"


def test_new_window_counts_as_foreground():
    s, _, (a, b), _, _ = make_sched(2)
    assert s.foreground() is b


def test_foreground_job_passes_queued_background_jobs():
    s, focus, (a, b), _, _ = make_sched(2)
    focus.note_input(a)
    submit(s, b, 1, "fond")
    submit(s, a, 2, "premier plan")
    assert order(s) == [(1, 2), (2, 1)]


def test_foreground_job_preempts_background_playback_and_it_is_replayed():
    s, focus, (a, b), evs, cuts = make_sched(2)
    focus.note_input(a)
    submit(s, b, 1, "fond, première phrase.", "fond, deuxième phrase.")
    playing = s.next_job(timeout=0.1)
    assert playing.window is b
    submit(s, a, 2, "premier plan")
    assert cuts.n == 1
    s.finish(playing)  # le lecteur rend la main après la coupure
    assert {"ev": "done", "id": 1} not in evs[1]
    assert order(s) == [(1, 2), (2, 1)]
    assert evs[1] == [{"ev": "done", "id": 1}]


def test_foreground_preempts_only_once_it_has_something_to_say():
    # sinon la fenêtre coupée serait reprise aussitôt, avant le premier segment de l'active
    s, focus, (a, b), _, cuts = make_sched(2)
    focus.note_input(a)
    submit(s, b, 1, "fond")
    s.next_job(timeout=0.1)
    submit(s, a, 2, close=False)
    assert cuts.n == 0
    s.segment(a, 2, "Succès.")
    assert cuts.n == 1


def test_background_window_keeps_only_its_latest_pending_announcement():
    s, focus, (a, b), evs, _ = make_sched(2)
    focus.note_input(a)
    submit(s, b, 1, "en cours de lecture")
    playing = s.next_job(timeout=0.1)
    submit(s, b, 2, "dépassée")
    submit(s, b, 3, "la plus récente")
    assert {"ev": "dropped", "id": 2} in evs[1]
    s.finish(playing)
    assert order(s) == [(2, 3)]


def test_foreground_window_keeps_all_its_announcements_in_order():
    s, focus, (a, b), _, _ = make_sched(2)
    focus.note_input(a)
    for jid in (1, 2, 3):
        submit(s, a, jid, f"phrase {jid}")
    assert order(s) == [(1, 1), (1, 2), (1, 3)]


def test_stop_cancels_only_its_own_window():
    s, focus, (a, b), evs, cuts = make_sched(2)
    focus.note_input(a)
    submit(s, a, 1, "a")
    submit(s, b, 2, "b")
    playing = s.next_job(timeout=0.1)
    s.stop(a)
    assert cuts.n == 1
    s.finish(playing)
    assert order(s) == [(2, 2)]


def test_stop_all_silences_every_window():
    s, focus, (a, b), evs, cuts = make_sched(2)
    focus.note_input(a)
    submit(s, b, 1, "b1")
    playing = s.next_job(timeout=0.1)
    submit(s, b, 2, "b2")
    s.stop(a, everyone=True)
    assert cuts.n == 1
    s.finish(playing)
    assert order(s) == []
    assert {"ev": "dropped", "id": 1} in evs[1] and {"ev": "dropped", "id": 2} in evs[1]


def test_job_without_any_segment_is_not_picked_yet():
    s, _, (a, b), _, _ = make_sched(2)
    submit(s, a, 1, close=False)
    assert s.next_job(timeout=0.05) is None
    s.segment(a, 1, "enfin")
    assert s.next_job(timeout=0.05).id == 1


def test_closing_a_window_cancels_its_speech():
    s, focus, (a, b), _, cuts = make_sched(2)
    submit(s, b, 1, "b1")
    playing = s.next_job(timeout=0.1)
    submit(s, b, 2, "b2")
    s.remove_window(b)
    assert cuts.n == 1
    s.finish(playing)
    assert order(s) == []


def test_wait_segment_returns_streamed_segments_then_none():
    s, _, (a,), _, _ = make_sched(1)
    submit(s, a, 1, "un", close=False)
    job = s.next_job(timeout=0.1)
    assert s.wait_segment(job, 0) == "un"
    threading.Timer(0.05, lambda: (s.segment(a, 1, "deux"), s.end(a, 1))).start()
    assert s.wait_segment(job, 1) == "deux"
    assert s.wait_segment(job, 2) is None


# ---------------------------------------------------------------- service réel, moteur factice

class FakeEngine:
    """Moteur de synthèse factice : « joue » chaque segment `seg_s` secondes et note
    l'intervalle ; `cut()` arrête le segment en cours comme le ferait un lecteur tué."""

    def __init__(self, seg_s: float = 0.03):
        self.seg_s = seg_s
        self.log: list[tuple[str, float, float]] = []
        self._gen = 0
        self._playing = False
        self.lock = threading.Lock()
        self.ctx = None

    def configure(self, voice, rate, language):
        self.ctx = (voice, rate, language)

    def play(self, texts):
        gen = self._gen
        for text in texts:
            if gen != self._gen:
                return
            with self.lock:
                start = time.monotonic()
                self._playing = True
            deadline = start + self.seg_s
            while time.monotonic() < deadline and gen == self._gen:
                time.sleep(0.002)
            with self.lock:
                self._playing = False
                self.log.append((text, start, time.monotonic()))

    def cut(self):
        self._gen += 1

    def playing(self):
        return self._playing

    def prewarm(self, busy, extra=()):
        pass


@pytest.fixture
def sock_path():
    d = Path(os.environ.get("TMPDIR_SHORT", "/tmp")) / f"sv-{os.getpid()}-{time.monotonic_ns()}"
    d.mkdir()
    yield str(d / "voice.sock")
    shutil.rmtree(d, ignore_errors=True)


def start_service(path: str, engine=None, idle_exit: float = 30.0, focus=None) -> VoiceService:
    engine = engine or FakeEngine()
    svc = VoiceService(path, engine_factory=lambda: engine, focus=focus or Focus(probe=lambda: None),
                       idle_exit=idle_exit)
    svc.start()
    return svc


def client(path: str, tty: str = "/dev/ttys001", spawn=None, **cfg_kw) -> VoiceClient:
    cfg = Config(**cfg_kw)
    return VoiceClient(cfg, path=path, spawn=spawn or (lambda: None), tty=tty)


def wait_idle(*clients, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    time.sleep(0.05)
    while any(c.speaking.is_set() or not c._q.empty() for c in clients) and time.time() < deadline:
        time.sleep(0.01)


def spoken(engine) -> list[str]:
    return [t for t, _, _ in engine.log]


def test_two_windows_never_speak_at_the_same_time(sock_path):
    engine = FakeEngine(seg_s=0.03)
    svc = start_service(sock_path, engine)
    a, b = client(sock_path, "/dev/ttys001"), client(sock_path, "/dev/ttys002")
    try:
        for i in range(3):
            a.say(f"Fenêtre A, phrase {i}.", interrupt=False)
            b.say(f"Fenêtre B, phrase {i}.", interrupt=False)
        wait_idle(a, b)
        spans = sorted((s, e) for _, s, e in engine.log)
        assert len(spans) >= 4
        assert all(e1 <= s2 for (_, e1), (s2, _) in zip(spans, spans[1:]))
    finally:
        a.close(), b.close(), svc.close()


def test_foreground_window_is_heard_first_and_background_is_named(sock_path):
    engine = FakeEngine(seg_s=0.05)
    focus = Focus(probe=lambda: None)
    svc = start_service(sock_path, engine, focus=focus)
    a, b = client(sock_path, "/dev/ttys001"), client(sock_path, "/dev/ttys002")
    try:
        a.note_input()
        time.sleep(0.1)
        b.say("Compilation terminée.")
        a.say("Succès.")
        wait_idle(a, b)
        said = spoken(engine)
        # selon l'instant où « Succès. » arrive, la fenêtre 2 n'a pas commencé ou elle est
        # coupée puis rejouée en entier : dans les deux cas elle finit, nommée, après
        assert said[-2:] == ["Fenêtre 2 :", "Compilation terminée."]
        assert "Succès." in said[:-2]
        assert "Fenêtre 1 :" not in said
    finally:
        a.close(), b.close(), svc.close()


def test_client_keeps_the_speaker_contract(sock_path):
    engine = FakeEngine()
    svc = start_service(sock_path, engine)
    a = client(sock_path)
    try:
        got = []
        a.say("37 éléments affichés : abrt, adjtime.", on_done=got.append)
        wait_idle(a)
        assert got == ["37 éléments affichés : abrt, adjtime."]
        assert a.last_text == got[0]
        assert not a.speaking.is_set()
        assert len(spoken(engine)) >= 2  # premier segment court (P19), coupé côté fenêtre
    finally:
        a.close(), svc.close()


def test_muted_window_sends_nothing_unless_forced(sock_path):
    engine = FakeEngine()
    svc = start_service(sock_path, engine)
    a = client(sock_path, tts_enabled=False)
    try:
        a.say("jamais")
        wait_idle(a)
        assert spoken(engine) == []
        a.say("toujours", force=True)
        wait_idle(a)
        assert spoken(engine) == ["toujours"]
    finally:
        a.close(), svc.close()


def test_window_gets_its_number(sock_path):
    svc = start_service(sock_path)
    a, b = client(sock_path, "/dev/ttys001"), client(sock_path, "/dev/ttys002")
    try:
        assert (a.window, b.window) == (1, 2)
    finally:
        a.close(), b.close(), svc.close()


def test_stop_all_from_one_window_silences_another(sock_path):
    engine = FakeEngine(seg_s=0.3)
    svc = start_service(sock_path, engine)
    a, b = client(sock_path, "/dev/ttys001"), client(sock_path, "/dev/ttys002")
    try:
        b.say("Une longue annonce. Une autre phrase. Et encore une.")
        deadline = time.time() + 2
        while not engine.playing() and time.time() < deadline:
            time.sleep(0.01)
        a.stop_all()
        wait_idle(a, b, timeout=1.0)
        assert len(engine.log) <= 2  # au plus le segment coupé et le nom de fenêtre
        assert not b.speaking.is_set()
    finally:
        a.close(), b.close(), svc.close()


def test_status_reports_the_window_being_heard(sock_path):
    engine = FakeEngine(seg_s=0.5)
    svc = start_service(sock_path, engine)
    a = client(sock_path)
    try:
        a.say("Une annonce.")
        deadline = time.time() + 2
        status = {}
        while time.time() < deadline:
            status = VoiceService.request_status(sock_path)
            if status.get("playing_pid"):
                break
            time.sleep(0.01)
        assert status["playing_pid"] == os.getpid()
        assert status["windows"][0]["n"] == 1
    finally:
        a.close(), svc.close()


def test_service_stops_when_the_last_window_closes(sock_path):
    svc = start_service(sock_path, idle_exit=0.1)
    a = client(sock_path)
    a.close()
    deadline = time.time() + 3
    while svc.running() and time.time() < deadline:
        time.sleep(0.02)
    assert not svc.running()
    assert not os.path.exists(sock_path)


def test_client_starts_the_service_on_demand(sock_path):
    started = []

    def spawn():
        started.append(start_service(sock_path))

    a = client(sock_path, spawn=spawn)
    try:
        assert len(started) == 1 and a.window == 1
        b = client(sock_path, "/dev/ttys002", spawn=spawn)
        assert len(started) == 1  # déjà en service : pas de second lancement
        b.close()
    finally:
        a.close()
        for s in started:
            s.close()


def test_client_restarts_a_dead_service_and_keeps_its_name(sock_path):
    engines, services = [], []

    def spawn():
        engines.append(FakeEngine())
        services.append(start_service(sock_path, engines[-1]))

    a = client(sock_path, "/dev/ttys001", spawn=spawn)
    b = client(sock_path, "/dev/ttys002", spawn=spawn)
    try:
        assert b.window == 2
        services[0].close()  # le service meurt
        time.sleep(0.1)
        b.say("Toujours là.")
        wait_idle(b)
        assert len(services) == 2
        assert "Toujours là." in spoken(engines[-1])
        assert b.window == 2
    finally:
        a.close(), b.close()
        for s in services:
            s.close()


def test_only_one_service_holds_the_lock(sock_path):
    lock = str(Path(sock_path).with_suffix(".lock"))
    first = acquire_lock(lock, wait=0)
    assert first is not None
    assert acquire_lock(lock, wait=0) is None
    os.close(first)
    second = acquire_lock(lock, wait=0)
    assert second is not None
    os.close(second)


def test_client_falls_back_to_local_voice_when_no_service(sock_path, monkeypatch):
    calls = []
    monkeypatch.setattr(VoiceClient, "connect_wait", 0.2)
    monkeypatch.setattr(VoiceClient, "_speak_locally", lambda self, texts, gen: calls.extend(texts))
    a = client(sock_path, spawn=lambda: None)
    try:
        a.say("Sans service.")
        wait_idle(a, timeout=8)
        assert calls == ["Sans service."]
    finally:
        a.close()


def test_input_ping_makes_the_window_foreground(sock_path):
    focus = Focus(probe=lambda: None)
    svc = start_service(sock_path, focus=focus)
    a, b = client(sock_path, "/dev/ttys001"), client(sock_path, "/dev/ttys002")
    try:
        a.note_input()
        deadline = time.time() + 2
        while (svc.sched.foreground() or b).n != 1 and time.time() < deadline:
            time.sleep(0.01)
        assert svc.sched.foreground().n == 1
    finally:
        a.close(), b.close(), svc.close()


# ---------------------------------------------------------------- bout en bout : vrai Piper, vrai processus

@pytest.mark.skipif(sys.platform != "darwin" or not REAL_VOICE.exists(),
                    reason="lecteur afplay (macOS) et voix Piper installée requis")
def test_real_service_process_plays_windows_one_after_another(tmp_path):
    """Vrai service (`python -m steph.voice_service`), vraie voix Piper ; seul le lecteur
    est remplacé par un faux `afplay` qui note son début et sa fin."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    played = tmp_path / "played.log"
    fake = bindir / "afplay"
    stamp = "$(perl -MTime::HiRes=time -e 'printf \"%.3f\", time')"
    fake.write_text(f"#!/bin/sh\necho \"start {stamp}\" >> {played}\nsleep 0.2\necho \"end {stamp}\" >> {played}\n")
    fake.chmod(0o755)
    rt = Path("/tmp") / f"sv-e2e-{os.getpid()}-{time.monotonic_ns()}"
    rt.mkdir()
    env_backup = dict(os.environ)
    try:
        os.environ["PATH"] = f"{bindir}:/usr/bin:/bin"
        os.environ["XDG_RUNTIME_DIR"] = str(rt)
        path = str(rt / "steph" / "voice.sock")
        from steph import voice_client
        cfg = dict(voice=str(REAL_VOICE))
        spawn = lambda: voice_client.spawn_service(path)  # noqa: E731
        a = VoiceClient(Config(**cfg), path=path, spawn=spawn, tty="/dev/ttys001")
        b = VoiceClient(Config(**cfg), path=path, spawn=spawn, tty="/dev/ttys002")
        try:
            a.say("Première fenêtre.")
            b.say("Deuxième fenêtre.")
            wait_idle(a, b, timeout=30)
            status = VoiceService.request_status(path)
            assert len(status["windows"]) == 2
        finally:
            a.close(), b.close()
        lines = played.read_text().split()
        events = [(lines[i], float(lines[i + 1])) for i in range(0, len(lines), 2)]
        depth, max_depth = 0, 0
        for kind, _ in sorted(events, key=lambda e: e[1]):
            depth += 1 if kind == "start" else -1
            max_depth = max(max_depth, depth)
        assert sum(1 for k, _ in events if k == "start") >= 2
        assert max_depth == 1  # jamais deux lecteurs en même temps
        deadline = time.time() + 5
        while (rt / "steph" / "voice.sock").exists() and time.time() < deadline:
            time.sleep(0.05)
        assert not (rt / "steph" / "voice.sock").exists()  # arrêt propre après la dernière fenêtre
    finally:
        os.environ.clear()
        os.environ.update(env_backup)
        shutil.rmtree(rt, ignore_errors=True)


# ---------------------------------------------------------------- moteur réel (Speaker) sous le service

def test_engine_prewarms_window_labels(monkeypatch):
    from test_tts_latency import FakeVoice, make_speaker, piper_key

    from steph.voice_service import SpeakerEngine

    voice = FakeVoice()
    make_speaker(monkeypatch, voice, prewarm=True)  # installe le faux lecteur
    engine = SpeakerEngine(Config(tts_enabled=False))
    engine.voice, engine.syn, engine.enabled = voice, None, True
    try:
        engine.prewarm(busy=lambda: False, extra=["Fenêtre 2 :"])
        assert piper_key("Fenêtre 2 :") in engine._cache
        assert piper_key("Succès.") in engine._cache
        n = len(voice.calls)
        engine.prewarm(busy=lambda: False, extra=["Fenêtre 2 :"])
        assert len(voice.calls) == n  # déjà fait : aucune nouvelle synthèse au repos
    finally:
        engine.close()


def test_engine_plays_a_job_on_one_player_and_cut_stops_it(monkeypatch):
    from test_tts_latency import FakeVoice, make_speaker

    from steph.voice_service import SpeakerEngine

    voice = FakeVoice()
    _, log, players = make_speaker(monkeypatch, voice, play_s=0.2)
    engine = SpeakerEngine(Config(tts_enabled=False))
    engine.voice, engine.syn, engine.enabled = voice, None, True
    try:
        t = threading.Thread(target=engine.play, args=(iter(["Un.", "Deux.", "Trois."]),))
        t.start()
        time.sleep(0.1)
        engine.cut()
        t.join(2)
        assert not t.is_alive()
        assert len(players) == 1
        assert len(log) < 3
    finally:
        engine.close()


def test_engine_configure_switches_rate_and_language_without_reloading_the_same_voice(monkeypatch):
    from steph.voice_service import SpeakerEngine

    engine = SpeakerEngine(Config(tts_enabled=False, voice="/v.onnx"))
    loads = []
    monkeypatch.setattr(engine, "_load_voice", lambda: loads.append(engine.cfg.voice))
    try:
        engine.configure("/v.onnx", 1.5, "en")
        assert (engine.cfg.speech_rate, engine.cfg.language, loads) == (1.5, "en", [])
        engine.configure("/w.onnx", 1.5, "en")
        assert loads == ["/w.onnx"]
    finally:
        engine.close()


# ---------------------------------------------------------------- fenêtre : touches, frappe, annonce d'ouverture

def test_in_process_speaker_has_the_shared_voice_api():
    from steph.tts import Speaker

    sp = Speaker(Config(tts_enabled=False))
    try:
        sp.note_input()  # sans effet hors service partagé
        sp.stop_all()
        assert sp._q.empty()
    finally:
        sp.close()


def test_stop_key_silences_every_window():
    from test_rules import make

    nar = make()
    calls = []
    nar.sp.stop_all = lambda: calls.append("all")
    nar._key("stop")
    assert calls == ["all"]


def test_typing_in_a_window_is_reported_to_the_voice():
    from steph.narrator import Narrator
    from steph.proxy import PtyProxy
    from steph.session import Session
    from test_rules import FakeLLM, FakeSpeaker

    sp = FakeSpeaker()
    notes = []
    sp.note_input = lambda: notes.append(1)
    nar = Narrator(Config(), Session(), sp, FakeLLM())
    proxy = PtyProxy(Config(), nar, "/tmp/unused.sock")
    proxy._on_input(b"l")
    assert notes == [1]


@pytest.mark.parametrize("language, n, expected", [
    ("fr", None, "Steph. F6 pour les paramètres."),
    ("fr", 1, "Steph. F6 pour les paramètres."),
    ("fr", 2, "Steph, fenêtre 2. F6 pour les paramètres."),
    ("en", 3, "Steph, window 3. F6 for settings."),
])
def test_opening_announcement_names_the_window_when_others_exist(language, n, expected):
    from steph.cli import opening_announcement

    assert opening_announcement(language, n) == expected


def test_engine_keeps_two_voices_loaded_for_windows_with_different_voices(monkeypatch):
    from steph.voice_service import SpeakerEngine

    engine = SpeakerEngine(Config(tts_enabled=False, voice="/v.onnx"))
    loads = []

    def fake_load():
        loads.append(engine.cfg.voice)
        engine.voice, engine.rate = f"voix {engine.cfg.voice}", 22050

    monkeypatch.setattr(engine, "_load_voice", fake_load)
    try:
        engine.voice = "voix /v.onnx"
        engine.configure("/w.onnx", 1.0, "fr")
        engine.configure("/v.onnx", 1.0, "fr")
        engine.configure("/w.onnx", 1.0, "fr")
        assert loads == ["/w.onnx"]  # aucun rechargement en alternant deux fenêtres
        assert engine.voice == "voix /w.onnx"
    finally:
        engine.close()
