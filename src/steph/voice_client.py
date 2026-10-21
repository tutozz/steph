"""Voix d'une fenêtre steph, jouée par le service vocal partagé (voice_service).

Même contrat que `Speaker` pour le narrateur, le menu et les touches : la fenêtre garde
son découpage (premier segment court), sa prononciation, son journal, son historique et
sa relecture ; seuls la synthèse et le lecteur audio partent dans le service. Service
absent et impossible à lancer : la fenêtre reprend sa propre voix Piper.
"""

from __future__ import annotations

import itertools
import json
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .config import Config
from .tts import Speaker
from .voice_service import SOCKET_PATH

INPUT_PING_INTERVAL = 0.3  # la frappe ne sert qu'à dater le focus : inutile d'écrire à chaque touche
OFFLINE_RETRY_S = 30.0  # service impossible à lancer : voix locale, nouvel essai plus tard


def spawn_service(path: str | Path | None = None) -> None:
    path = Path(path or SOCKET_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".log"), "ab") as log:
        subprocess.Popen([sys.executable, "-m", "steph.voice_service", "--socket", str(path)],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)


@dataclass
class _Sent:
    id: int
    voice: str
    rate: float
    lang: str
    segments: list[str] = field(default_factory=list)
    closed: bool = False


class VoiceClient(Speaker):
    connect_wait = 5.0  # premier lancement du service : démarrage de Python compris

    def __init__(self, cfg: Config, path: str | Path | None = None, spawn=None, tty: str = ""):
        self._path = str(path or SOCKET_PATH)
        self._spawn = spawn or (lambda: spawn_service(self._path))
        self._tty = tty
        self._io = threading.RLock()
        self._sock: socket.socket | None = None
        self._file = None
        self._jobs: dict[int, _Sent] = {}
        self._next_id = 0
        self._generating = False
        self._closing = False
        self._offline_until = 0.0
        self._last_input = 0.0
        self.window: int | None = None
        super().__init__(cfg)

    # ---------------------------------------------------------------- API
    def stop_all(self) -> None:
        self.stop()
        self._send_quiet({"op": "stop", "all": True})

    def note_input(self) -> None:
        now = time.monotonic()
        if now - self._last_input >= INPUT_PING_INTERVAL:
            self._last_input = now
            self._send_quiet({"op": "input"})

    def close(self) -> None:
        self._closing = True
        super().close()
        with self._io:
            self._drop_connection()

    # ---------------------------------------------------------------- Speaker
    def _load_voice(self) -> None:
        if self.voice is not None:  # voix locale de secours déjà chargée
            Speaker._load_voice(self)
        elif self.enabled:
            self._ensure_connected()

    def _kill_player(self) -> None:
        if self.voice is not None:
            Speaker._kill_player(self)
        with self._io:
            self._jobs.clear()
        self._send_quiet({"op": "stop"})
        self._update_speaking()

    def _run(self) -> None:
        while True:
            utt = self._q.get()
            if utt is None:
                return
            gen = self._gen
            spoken: list[str] = []
            self._generating = True
            self.speaking.set()
            try:
                texts = self._segments(utt, gen, spoken)
                first = next(texts, None)
                if first is not None:
                    texts = itertools.chain([first], texts)
                    if self._ensure_connected():
                        self._send_utterance(texts, gen)
                    else:
                        self._speak_locally(texts, gen)
            except Exception:
                pass
            self._generating = False
            self._finish_utterance(utt, spoken)
            self._update_speaking()

    def _speak_locally(self, texts: Iterator[str], gen: int) -> None:
        if self.voice is None:
            Speaker._load_voice(self)
        Speaker._speak_all(self, texts, gen)

    # ---------------------------------------------------------------- envoi
    def _send_utterance(self, texts: Iterator[str], gen: int) -> None:
        with self._io:
            self._next_id += 1
            job = _Sent(self._next_id, self.cfg.voice, self.cfg.speech_rate, self.cfg.language)
            self._jobs[job.id] = job
            self._write({"op": "say", "id": job.id, "voice": job.voice, "rate": job.rate, "lang": job.lang})
        # une annonce écartée par le service est lue jusqu'au bout sans être envoyée :
        # son texte complet reste disponible pour F9 dans cette fenêtre
        for text in texts:
            with self._io:
                if gen != self._gen or job.id not in self._jobs:
                    continue
                job.segments.append(text)
                self._write({"op": "seg", "id": job.id, "text": text})
        with self._io:
            job.closed = True
            if job.id in self._jobs:
                self._write({"op": "end", "id": job.id})

    def _write(self, msg: dict) -> None:
        """Sous `_io`. Connexion perdue : on se reconnecte (en relançant le service) et
        la reconnexion renvoie toutes les annonces en cours, celle-ci comprise."""
        if self._sock is not None:
            try:
                self._file.write((json.dumps(msg, ensure_ascii=False) + "\n").encode())
                return
            except OSError:
                self._drop_connection()
        if not self._ensure_connected():
            self._jobs.clear()

    def _send_quiet(self, msg: dict) -> None:
        """Message sans suite (stop, frappe) : jamais de lancement de service pour lui."""
        with self._io:
            if self._sock is None:
                return
            try:
                self._file.write((json.dumps(msg) + "\n").encode())
            except OSError:
                self._drop_connection()

    # ---------------------------------------------------------------- connexion
    def _ensure_connected(self) -> bool:
        with self._io:
            if self._sock is not None:
                return True
            if self._closing or time.monotonic() < self._offline_until:
                return False
            if self._try_connect():
                return True
            try:
                self._spawn()
            except Exception:
                pass
            deadline = time.monotonic() + self.connect_wait
            while time.monotonic() < deadline:
                if self._try_connect():
                    return True
                time.sleep(0.05)
            self._offline_until = time.monotonic() + OFFLINE_RETRY_S
            return False

    def _try_connect(self) -> bool:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.settimeout(2.0)
            s.connect(self._path)
            f = s.makefile("rwb", buffering=0)
            hello = {"op": "hello", "tty": self._tty, "pid": os.getpid(), "want": self.window,
                     "lang": self.cfg.language}
            f.write((json.dumps(hello) + "\n").encode())
            reply = json.loads(f.readline() or b"{}")
            if reply.get("ev") != "hello":
                raise ValueError(reply)
            s.settimeout(None)
        except (OSError, ValueError):
            s.close()
            return False
        self._sock, self._file = s, f
        self.window = reply.get("n")
        threading.Thread(target=self._reader, args=(s, f), daemon=True, name="voice-reader").start()
        for job in list(self._jobs.values()):
            self._write({"op": "say", "id": job.id, "voice": job.voice, "rate": job.rate, "lang": job.lang})
            for text in job.segments:
                self._write({"op": "seg", "id": job.id, "text": text})
            if job.closed:
                self._write({"op": "end", "id": job.id})
        return True

    def _drop_connection(self) -> None:
        s, self._sock, self._file = self._sock, None, None
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            s.close()

    def _reader(self, s: socket.socket, f) -> None:
        try:
            for line in f:
                msg = json.loads(line)
                if msg.get("ev") in ("done", "dropped"):
                    with self._io:
                        self._jobs.pop(msg.get("id"), None)
                    self._update_speaking()
        except (OSError, ValueError):
            pass
        with self._io:
            if self._sock is not s:
                return
            self._drop_connection()
            # service mort : les annonces en attente repartent vers un service relancé
            if self._jobs and not self._closing and not self._ensure_connected():
                self._jobs.clear()
        self._update_speaking()

    def _update_speaking(self) -> None:
        with self._io:
            busy = bool(self._jobs) or self._generating or not self._q.empty()
        if busy:
            self.speaking.set()
        else:
            self.speaking.clear()
