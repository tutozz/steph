"""Fenêtre au premier plan, pour la voix partagée entre fenêtres.

Deux indices, le plus récent l'emporte :
- la sonde du système : sur macOS, le terminal au premier plan (Terminal, iTerm2) donne
  le tty de son onglet actif ;
- la frappe : on ne tape que dans la fenêtre qui a le focus.

Linux : pas de sonde. Sous Wayland, le focus n'est pas lisible par un client ; sous X11,
la fenêtre active donne un processus de terminal souvent commun à toutes les fenêtres
(gnome-terminal-server, konsole), sans lien fiable avec un pty. La frappe suffit.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from typing import Callable, Hashable

TERMINAL_SCRIPTS = {
    "Terminal": 'tell application "Terminal" to tty of selected tab of front window',
    "iTerm2": 'tell application "iTerm2" to tty of current session of current window',
}
# osascript coûte ~0,1 s : jamais plus souvent, et jamais sur le chemin d'une annonce
MIN_PROBE_INTERVAL = 0.5
_NAME = re.compile(r'^"([^"]+)"')


def parse_front_app(out: str) -> str | None:
    m = _NAME.match(out.strip())
    return m.group(1) if m else None


def frontmost_tty(run: Callable = subprocess.run) -> str | None:
    """tty de l'onglet actif du terminal au premier plan, ou None."""
    if sys.platform != "darwin":
        return None
    try:
        asn = run(["lsappinfo", "front"], capture_output=True, text=True, timeout=1).stdout.strip()
        app = parse_front_app(run(["lsappinfo", "info", "-only", "name", asn],
                                  capture_output=True, text=True, timeout=1).stdout)
        script = TERMINAL_SCRIPTS.get(app or "")
        if script is None:
            return None  # un script vers une application fermée la lancerait
        tty = run(["osascript", "-e", script], capture_output=True, text=True, timeout=2).stdout.strip()
        return tty or None
    except (OSError, subprocess.SubprocessError):
        return None


class Focus:
    def __init__(self, probe: Callable[[], str | None] = frontmost_tty,
                 clock: Callable[[], float] = time.monotonic, min_interval: float = MIN_PROBE_INTERVAL):
        self._probe = probe
        self._clock = clock
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._typed: tuple[Hashable, float] | None = None
        self._probed: tuple[str, float] | None = None
        self._probe_started = float("-inf")
        self._probing = False

    def note_input(self, key: Hashable) -> None:
        with self._lock:
            self._typed = (key, self._clock())

    def forget(self, key: Hashable) -> None:
        with self._lock:
            if self._typed and self._typed[0] == key:
                self._typed = None

    def refresh(self, wait: bool = False) -> None:
        """Relance la sonde en tâche de fond, au plus une fois par `min_interval`."""
        with self._lock:
            now = self._clock()
            if self._probing or now - self._probe_started < self._min_interval:
                return
            self._probing = True
            self._probe_started = now
        t = threading.Thread(target=self._run_probe, daemon=True, name="focus-probe")
        t.start()
        if wait:
            t.join()

    def _run_probe(self) -> None:
        try:
            tty = self._probe()
        except Exception:
            tty = None
        with self._lock:
            self._probing = False
            if tty:
                self._probed = (tty, self._clock())

    def foreground(self, ttys: dict[Hashable, str]) -> Hashable | None:
        """Parmi `ttys` (fenêtre -> tty), celle qui a le focus, ou None."""
        with self._lock:
            typed, probed = self._typed, self._probed
        typed_key = typed[0] if typed and typed[0] in ttys else None
        if probed:
            match = next((k for k, tty in ttys.items() if tty and tty == probed[0]), None)
            if match is not None and (typed_key is None or probed[1] >= typed[1]):
                return match
        return typed_key
