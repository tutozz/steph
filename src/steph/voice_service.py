"""Service vocal partagé : une seule voix Piper, une seule file de lecture pour toutes
les fenêtres steph d'un utilisateur.

Lancé à la demande par la première fenêtre (`voice_client.spawn_service`), unique grâce à
un verrou, arrêté quand la dernière fenêtre se ferme. Chaque fenêtre découpe et normalise
son texte (prononciation, premier segment court) et envoie des segments prêts à synthétiser.

Règles de file :
- la fenêtre au premier plan passe devant les autres ; si une autre fenêtre parle, elle
  est coupée et son annonce est rejouée ensuite, en entier ;
- une annonce d'une autre fenêtre commence par son nom (« Fenêtre 2 : ») ;
- une fenêtre en arrière-plan ne garde qu'une annonce en attente, la plus récente : une
  annonce plus récente de la même fenêtre rend la précédente caduque (la fin d'une
  commande remplace son point d'étape), et une file qui s'allonge retarderait la fenêtre
  active. La fenêtre au premier plan garde toutes les siennes, dans l'ordre.

Protocole : lignes JSON sur un socket Unix. Fenêtre -> service : hello, say, seg, end,
stop, input. Service -> fenêtre : hello (numéro), done, dropped. Une connexion qui
commence par `status` reçoit l'état courant (mesures, diagnostic).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import socket
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

from .config import RUNTIME_DIR, load_config
from .focus import Focus
from .strings import t as _t
from .tts import Speaker, normalize_for_speech

SOCKET_PATH = RUNTIME_DIR / "voice.sock"
IDLE_EXIT_S = 2.0  # délai avant arrêt quand plus aucune fenêtre n'est connectée
LOCK_WAIT_S = 5.0  # un service qui s'arrête peut encore tenir le verrou
MAX_EXTRA_VOICES = 1  # deux voix en mémoire au plus : ~100 Mo chacune


def window_label(language: str, n: int) -> str:
    return _t(language, "voice.window_label").format(n=n)


@dataclass(eq=False)
class Window:
    n: int
    tty: str
    pid: int
    send: Callable[[dict], None]
    lang: str = "fr"


@dataclass(eq=False)
class Job:
    id: int
    window: Window
    voice: str
    rate: float
    lang: str
    segments: list[str] = field(default_factory=list)
    closed: bool = False
    cancelled: bool = False
    preempted: bool = False

    def ready(self) -> bool:
        return bool(self.segments) or self.closed

    def live(self) -> bool:
        return not (self.cancelled or self.preempted)


class Scheduler:
    """État de la file, sans audio ni socket. Tout passe sous `cond`."""

    def __init__(self, focus: Focus, on_cut: Callable[[], None] = lambda: None):
        self.focus = focus
        self.on_cut = on_cut
        self.cond = threading.Condition()
        self.windows: list[Window] = []
        self.pending: list[Job] = []
        self.current: Job | None = None

    # ------------------------------------------------------------ fenêtres
    def add_window(self, tty: str, pid: int, send: Callable[[dict], None], want: int | None = None,
                   lang: str = "fr") -> Window:
        with self.cond:
            used = {w.n for w in self.windows}
            n = want if want and want not in used else next(i for i in range(1, len(used) + 2) if i not in used)
            w = Window(n=n, tty=tty, pid=pid, send=send, lang=lang)
            self.windows.append(w)
            self.focus.note_input(w)  # une fenêtre qu'on vient d'ouvrir a le focus
            self.cond.notify_all()
            return w

    def remove_window(self, w: Window) -> None:
        with self.cond:
            if w in self.windows:
                self.windows.remove(w)
            self.focus.forget(w)
            self._cancel(lambda j: j.window is w, notify=False)

    def foreground(self) -> Window | None:
        with self.cond:
            return self.focus.foreground({w: w.tty for w in self.windows})

    def prefix(self, job: Job) -> str | None:
        with self.cond:
            if len(self.windows) < 2 or self.foreground() is job.window:
                return None
            return window_label(job.lang, job.window.n)

    def labels(self) -> list[str]:
        with self.cond:
            return [window_label(w.lang, w.n) for w in self.windows] if len(self.windows) >= 2 else []

    # ------------------------------------------------------------ annonces
    def submit(self, w: Window, jid: int, voice: str, rate: float, lang: str) -> Job:
        job = Job(id=jid, window=w, voice=voice, rate=rate, lang=lang)
        with self.cond:
            w.lang = lang
            if len(self.windows) >= 2:
                self.focus.refresh()
            if self.foreground() is not w:
                self._drop_pending(w)
            self.pending.append(job)
            self.cond.notify_all()
        return job

    def segment(self, w: Window, jid: int, text: str) -> None:
        with self.cond:
            job = self._find(w, jid)
            if job is not None:
                job.segments.append(text)
                self._preempt_for(job)
                self.cond.notify_all()

    def end(self, w: Window, jid: int) -> None:
        with self.cond:
            job = self._find(w, jid)
            if job is not None:
                job.closed = True
                self._preempt_for(job)
                self.cond.notify_all()

    def stop(self, w: Window, everyone: bool = False) -> None:
        with self.cond:
            self._cancel(lambda j: j.window is w, notify=False)
            if everyone:
                self._cancel(lambda j: j.window is not w, notify=True)

    def has_work(self) -> bool:
        with self.cond:
            return any(j.ready() for j in self.pending)

    # ------------------------------------------------------------ lecteur
    def next_job(self, timeout: float) -> Job | None:
        """Prochaine annonce à dire : la fenêtre au premier plan d'abord, puis l'ordre
        d'arrivée. Une annonce sans aucun segment n'occupe pas la voix."""
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                ready = [j for j in self.pending if j.ready()]
                if ready:
                    fg = self.foreground()
                    job = next((j for j in ready if j.window is fg), ready[0])
                    self.pending.remove(job)
                    self.current = job
                    return job
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self.cond.wait(left)

    def wait_segment(self, job: Job, i: int, poll: float = 0.25) -> str | None:
        """Segment n° i de `job`, en attendant qu'il arrive ; None à la fin de l'annonce
        ou si elle est coupée."""
        with self.cond:
            while job.live():
                if i < len(job.segments):
                    return job.segments[i]
                if job.closed:
                    return None
                self.cond.wait(poll)
            return None

    def finish(self, job: Job) -> None:
        with self.cond:
            if self.current is job:
                self.current = None
            if job.cancelled:
                pass
            elif job.preempted:
                job.preempted = False
                if any(j.window is job.window for j in self.pending):
                    job.window.send({"ev": "dropped", "id": job.id})
                else:
                    self.pending.insert(0, job)  # rejouée en entier après la fenêtre active
            else:
                job.window.send({"ev": "done", "id": job.id})
            self.cond.notify_all()

    # ------------------------------------------------------------ interne
    def _find(self, w: Window, jid: int) -> Job | None:
        if self.current is not None and self.current.window is w and self.current.id == jid:
            return self.current
        return next((j for j in self.pending if j.window is w and j.id == jid), None)

    def _preempt_for(self, job: Job) -> None:
        """Coupe une autre fenêtre en train de parler, dès que l'annonce de la fenêtre au
        premier plan a de quoi être dite (pas avant : la coupée serait reprise aussitôt)."""
        cur = self.current
        if (job in self.pending and cur is not None and cur.window is not job.window and cur.live()
                and self.foreground() is job.window):
            cur.preempted = True
            self.on_cut()

    def _drop_pending(self, w: Window) -> None:
        for j in [j for j in self.pending if j.window is w]:
            self.pending.remove(j)
            j.cancelled = True
            w.send({"ev": "dropped", "id": j.id})

    def _cancel(self, match: Callable[[Job], bool], notify: bool) -> None:
        for j in [j for j in self.pending if match(j)]:
            self.pending.remove(j)
            j.cancelled = True
            if notify:
                j.window.send({"ev": "dropped", "id": j.id})
        cur = self.current
        if cur is not None and match(cur) and not cur.cancelled:
            cur.cancelled = True
            if notify:
                cur.window.send({"ev": "dropped", "id": cur.id})
            self.on_cut()
        self.cond.notify_all()


class SpeakerEngine(Speaker):
    """Le Speaker d'une fenêtre, réduit à son moteur : voix Piper, cache des statuts,
    premier segment sans silence, lecture en flux. Le service le pilote ; il n'a pas
    de file ni de thread à lui."""

    def __init__(self, cfg):
        self._voices: OrderedDict[str, tuple] = OrderedDict()  # voix d'autres fenêtres, déjà chargées
        super().__init__(cfg)

    def _run(self) -> None:
        return

    def configure(self, voice: str, rate: float, language: str) -> None:
        if voice and voice != self.cfg.voice:
            if self.voice is not None:
                self._voices[self.cfg.voice] = (self.voice, self.rate)
            cached = self._voices.pop(voice, None)
            if cached is not None:
                self.cfg.voice = voice
                self.voice, self.rate = cached
            else:
                self.reload_voice(voice)
            while len(self._voices) > MAX_EXTRA_VOICES:
                self._voices.popitem(last=False)
        if rate != self.cfg.speech_rate:
            self.set_rate(rate)
        self.cfg.language = language

    def play(self, texts: Iterable[str]) -> None:
        self._speak_all(iter(texts), self._gen)

    def cut(self) -> None:
        self.stop()

    def playing(self) -> bool:
        p = self._proc
        return p is not None and p.poll() is None

    def prewarm(self, busy: Callable[[], bool], extra: Iterable[str] = ()) -> None:
        self._prewarm_idle(busy, extra)


def acquire_lock(path: str, wait: float = LOCK_WAIT_S) -> int | None:
    """Verrou exclusif tenu toute la vie du service : un seul service par utilisateur."""
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + wait
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except OSError:
            if time.monotonic() >= deadline:
                os.close(fd)
                return None
            time.sleep(0.05)


class VoiceService:
    def __init__(self, path: str, engine_factory: Callable[[], object], focus: Focus | None = None,
                 idle_exit: float = IDLE_EXIT_S):
        self.path = path
        self.engine_factory = engine_factory
        self.engine = None
        self.idle_exit = idle_exit
        self.sched = Scheduler(focus or Focus(), on_cut=self._cut)
        self._closed = threading.Event()
        self._closing = False
        self._engine_ready = threading.Event()
        self._idle_timer: threading.Timer | None = None
        self._conns: set[socket.socket] = set()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(path)
        os.chmod(path, 0o600)
        self.sock.listen(16)

    # ------------------------------------------------------------ vie du service
    def start(self) -> None:
        threading.Thread(target=self._accept, daemon=True, name="voice-accept").start()
        threading.Thread(target=self._player, daemon=True, name="voice-player").start()
        self._schedule_idle_exit()  # lancé pour une fenêtre qui n'est jamais venue

    def serve_forever(self) -> None:
        self.start()
        self._closed.wait()

    def running(self) -> bool:
        return not self._closed.is_set()

    def close(self) -> None:
        with self.sched.cond:
            if self._closing:
                return
            self._closing = True
        try:
            self.sock.close()
        except OSError:
            pass
        try:
            os.unlink(self.path)
        except OSError:
            pass
        for c in list(self._conns):
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        with self.sched.cond:
            for w in list(self.sched.windows):
                self.sched.remove_window(w)
        self._cut()
        with self.sched.cond:
            # en dernier : serve_forever rend la main, le processus peut s'arrêter
            self._closed.set()
            self.sched.cond.notify_all()

    def _cut(self) -> None:
        if self.engine is not None:
            self.engine.cut()

    def _schedule_idle_exit(self) -> None:
        with self.sched.cond:
            if self.sched.windows or self._closing:
                return
            if self._idle_timer is not None:
                self._idle_timer.cancel()
            self._idle_timer = threading.Timer(self.idle_exit, self._exit_if_idle)
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def _exit_if_idle(self) -> None:
        with self.sched.cond:
            if self.sched.windows:
                return
        self.close()

    # ------------------------------------------------------------ lecteur
    def _player(self) -> None:
        try:
            self.engine = self.engine_factory()
        finally:
            self._engine_ready.set()
        while not self._closed.is_set():
            job = self.sched.next_job(timeout=1.0)
            if job is None:
                if not self._closed.is_set():
                    try:
                        self.engine.prewarm(self.sched.has_work, self.sched.labels())
                    except Exception as e:
                        self._log(f"préchauffage : {e!r}")
                continue
            try:
                self.engine.configure(job.voice, job.rate, job.lang)
                self.engine.play(self._texts(job, self.sched.prefix(job)))
            except Exception as e:
                self._log(f"lecture : {e!r}")
            self.sched.finish(job)

    def _texts(self, job: Job, label: str | None) -> Iterator[str]:
        if label and job.live():
            yield normalize_for_speech(label)
        i = 0
        while True:
            seg = self.sched.wait_segment(job, i)
            if seg is None:
                return
            yield seg
            i += 1

    # ------------------------------------------------------------ connexions
    def _accept(self) -> None:
        while not self._closed.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True, name="voice-conn").start()

    def _serve(self, conn: socket.socket) -> None:
        self._conns.add(conn)
        f = conn.makefile("rwb", buffering=0)
        lock = threading.Lock()

        def send(obj: dict) -> None:
            with lock:
                try:
                    f.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
                except OSError:
                    pass

        w = None
        try:
            hello = json.loads(f.readline() or b"{}")
            if hello.get("op") == "status":
                send(self.status())
                return
            if hello.get("op") != "hello":
                return
            w = self.sched.add_window(tty=hello.get("tty", ""), pid=int(hello.get("pid", 0)), send=send,
                                      want=hello.get("want"), lang=hello.get("lang", "fr"))
            send({"ev": "hello", "n": w.n})
            for line in f:
                self._dispatch(w, json.loads(line))
        except (OSError, ValueError) as e:
            self._log(f"connexion : {e!r}")
        finally:
            self._conns.discard(conn)
            if w is not None:
                self.sched.remove_window(w)
                self._schedule_idle_exit()
            try:
                conn.close()
            except OSError:
                pass

    def _dispatch(self, w: Window, msg: dict) -> None:
        op = msg.get("op")
        if op == "say":
            self.sched.submit(w, int(msg["id"]), msg.get("voice", ""), float(msg.get("rate", 1.0)),
                              msg.get("lang", "fr"))
        elif op == "seg":
            self.sched.segment(w, int(msg["id"]), msg.get("text", ""))
        elif op == "end":
            self.sched.end(w, int(msg["id"]))
        elif op == "stop":
            self.sched.stop(w, everyone=bool(msg.get("all")))
        elif op == "input":
            self.sched.focus.note_input(w)
            if len(self.sched.windows) >= 2:
                self.sched.focus.refresh()

    def status(self) -> dict:
        with self.sched.cond:
            cur = self.sched.current
            playing = cur is not None and cur.live() and self.engine is not None and self.engine.playing()
            fg = self.sched.foreground()
            return {
                "pid": os.getpid(),
                "playing_pid": cur.window.pid if playing else None,
                "foreground_pid": fg.pid if fg else None,
                "pending": len(self.sched.pending),
                "windows": [{"n": w.n, "pid": w.pid, "tty": w.tty} for w in self.sched.windows],
            }

    @staticmethod
    def request_status(path: str, timeout: float = 1.0) -> dict:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect(path)
                s.sendall(b'{"op": "status"}\n')
                line = s.makefile("rb").readline()
                return json.loads(line) if line else {}
        except (OSError, ValueError):
            return {}

    def _log(self, msg: str) -> None:
        print(time.strftime("%H:%M:%S ") + msg, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="steph-voice")
    ap.add_argument("--socket", default=str(SOCKET_PATH))
    args = ap.parse_args(argv)
    path = Path(args.socket)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(str(path.with_suffix(".lock")))
    if lock is None:
        return 0  # un autre service tient la voix
    cfg = load_config()
    cfg.tts_enabled = True  # chaque fenêtre décide de ce qu'elle envoie
    service = VoiceService(str(path), engine_factory=lambda: SpeakerEngine(cfg))
    path.with_suffix(".pid").write_text(str(os.getpid()))
    try:
        service.serve_forever()
    finally:
        path.with_suffix(".pid").unlink(missing_ok=True)
        os.close(lock)
    return 0


if __name__ == "__main__":
    sys.exit(main())
