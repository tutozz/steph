"""Téléchargement de l'installation, lisible au lecteur d'écran.

`python -m steph.fetch --label Modèle URL DEST` : curl fait le transfert (reprise,
proxy, certificats du système) en silence ; ce module écrit une ligne de texte à
chaque dizaine de pour cent, avec la durée restante estimée, au lieu de la barre
de curl réécrite en `\\r`. Avec `--speak`, steph dit aussi l'avancement tous les
25 %. Le fichier reste en `.part` tant qu'il n'est pas complet.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

from .strings import t

QUARTERS = (25, 50, 75)
UNKNOWN_SIZE_INTERVAL = 30.0


def remaining(seconds: float, language: str) -> str:
    if seconds < 60:
        return t(language, "fetch.seconds").format(n=max(10, round(seconds / 10) * 10))
    if seconds < 90:
        return t(language, "fetch.minute")
    return t(language, "fetch.minutes").format(n=int(seconds / 60 + 0.5))


class Progress:
    """Décide quoi écrire et quoi dire ; aucune E/S."""

    def __init__(self, label: str, total: int | None, start_bytes: int, language: str, now: float):
        self.label, self.total, self.language = label, total, language
        self.start_bytes, self.t0 = start_bytes, now
        self.last_decile = self._pct(start_bytes) // 10 * 10 if total else 0
        self.last_quarter = max((q for q in QUARTERS if q <= self._pct(start_bytes)), default=0) if total else 0
        self.last_line_at = now

    def _pct(self, size: int) -> int:
        return min(100, size * 100 // self.total) if self.total else 0

    def update(self, size: int, now: float) -> tuple[list[str], list[str]]:
        if not self.total:
            if now - self.last_line_at < UNKNOWN_SIZE_INTERVAL:
                return [], []
            self.last_line_at = now
            return [t(self.language, "fetch.progress_unknown").format(label=self.label, mb=size >> 20)], []
        pct = self._pct(size)
        elapsed = max(now - self.t0, 1e-6)
        speed = (size - self.start_bytes) / elapsed
        eta = remaining((self.total - size) / speed, self.language) if speed > 0 else "?"

        def text(p: int) -> str:
            return t(self.language, "fetch.progress").format(label=self.label, pct=p, eta=eta)

        # plusieurs paliers franchis d'un coup : seul le dernier est écrit ou dit,
        # une rafale de lignes identiques n'apprend rien au lecteur d'écran
        decile = min(pct, 99) // 10 * 10
        lines, spoken = [], []
        if decile > self.last_decile:
            self.last_decile = decile
            lines.append(text(decile))
        quarter = max((q for q in QUARTERS if q <= pct), default=0)
        if quarter > self.last_quarter:
            self.last_quarter = quarter
            spoken.append(text(quarter))
        return lines, spoken


def remote_size(url: str) -> int | None:
    """Taille annoncée par le serveur, après redirections (Hugging Face, GitHub)."""
    try:
        r = subprocess.run(["curl", "-q", "-sIL", "--max-time", "20", url], capture_output=True, text=True,
                           timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    size = None
    for line in r.stdout.splitlines():
        name, _, value = line.partition(":")
        if name.strip().lower() == "content-length" and value.strip().isdigit():
            size = int(value.strip())  # la dernière réponse de la chaîne fait foi
    return size or None


class _Voice:
    def __init__(self, enabled: bool):
        self.speaker = None
        if not enabled:
            return
        try:
            from .config import load_config
            from .tts import Speaker

            # voix coupée (STEPH_TTS_ENABLED=0) : Speaker ne parle pas mais journalise
            self.speaker = Speaker(load_config())
        except Exception:
            self.speaker = None

    def say(self, text: str) -> None:
        if self.speaker:
            self.speaker.say(text, interrupt=False)

    def close(self) -> None:
        if not self.speaker:
            return
        time.sleep(0.2)
        while self.speaker.speaking.is_set() or not self.speaker._q.empty():
            time.sleep(0.05)
        self.speaker.close()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _finish(part: Path, dest: Path, label: str, language: str, sha256: str | None) -> bool:
    if sha256 and _sha256(part) != sha256.lower():
        part.unlink()
        print(t(language, "fetch.bad_hash").format(label=label), flush=True)
        return False
    os.replace(part, dest)
    return True


def download(url: str, dest: Path, label: str, language: str, speak: bool, poll: float, retries: int,
             sha256: str | None = None) -> int:
    part = dest.with_name(dest.name + ".part")
    total = remote_size(url)
    start = part.stat().st_size if part.exists() else 0
    if total and start == total:
        # coupure juste avant le renommage : rien à retélécharger
        if not _finish(part, dest, label, language, sha256):
            return 1
        print(t(language, "fetch.done").format(label=label), flush=True)
        return 0
    if total and start > total:
        part.unlink()  # .part plus grand que prévu : fichier distant changé, on repart de zéro
        start = 0
    voice = _Voice(speak)
    progress = Progress(label, total, start, language, time.monotonic())
    cmd = ["curl", "-q", "-fL", "-sS", "--retry", str(retries), "-C", "-", "-o", str(part), url]
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
        while True:
            code = proc.poll()
            size = part.stat().st_size if part.exists() else 0
            lines, spoken = progress.update(size, time.monotonic())
            if code is not None:
                lines, spoken = [], []  # fini entre deux relevés : « téléchargé » suffit
            for line in lines:
                print(line, flush=True)
            for s in spoken:
                voice.say(s)
            if code is not None:
                break
            time.sleep(poll)
        if code != 0 or (total and part.stat().st_size != total):
            print(t(language, "fetch.failed").format(label=label), flush=True)
            return code or 1
        if not _finish(part, dest, label, language, sha256):
            return 1
        print(t(language, "fetch.done").format(label=label), flush=True)
        voice.say(t(language, "fetch.done").format(label=label))
        return 0
    finally:
        voice.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m steph.fetch")
    p.add_argument("--label", required=True)
    p.add_argument("--lang", default="fr")
    p.add_argument("--speak", action="store_true", help="dire l'avancement tous les 25 %%")
    p.add_argument("--poll", type=float, default=1.0)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--sha256", help="empreinte attendue ; fichier supprimé si elle diffère")
    p.add_argument("url")
    p.add_argument("dest")
    a = p.parse_args(argv)
    return download(a.url, Path(a.dest), a.label, a.lang, a.speak, a.poll, a.retries, a.sha256)


if __name__ == "__main__":
    sys.exit(main())
