"""Lecture audio multi-plateforme.

Linux : flux brut vers paplay / pw-play / aplay (le son démarre dès le premier
morceau synthétisé). macOS : flux vers `play` (sox) s'il est installé, sinon
fichier WAV temporaire lu par `afplay` (livré avec le système).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import wave

IS_MAC = sys.platform == "darwin"


def stream_player_cmd(rate: int) -> list[str] | None:
    """Commande qui lit du PCM 16 bits mono sur stdin, ou None."""
    if shutil.which("paplay") and not IS_MAC:
        return ["paplay", "--raw", "--format=s16le", f"--rate={rate}", "--channels=1",
                "--client-name=steph", "--stream-name=voix"]
    if shutil.which("pw-play") and not IS_MAC:
        return ["pw-play", "--format=s16", f"--rate={rate}", "--channels=1", "-"]
    if shutil.which("play"):  # sox (brew install sox)
        return ["play", "-q", "-t", "raw", "-r", str(rate), "-e", "signed", "-b", "16", "-c", "1", "-"]
    if shutil.which("aplay") and not IS_MAC:
        return ["aplay", "-q", "-f", "S16_LE", "-r", str(rate), "-c", "1"]
    return None


def file_player_cmd(path: str) -> list[str] | None:
    if shutil.which("afplay"):
        return ["afplay", path]
    if shutil.which("paplay"):
        return ["paplay", path]
    return None


def write_wav(pcm: bytes, rate: int) -> str:
    fd, path = tempfile.mkstemp(prefix="steph-", suffix=".wav")
    with os.fdopen(fd, "wb") as f, wave.open(f, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return path


def system_voice_cmd(text: str) -> list[str] | None:
    """Voix du système, en secours si Piper n'est pas disponible."""
    if IS_MAC and shutil.which("say"):
        return ["say", "-v", os.environ.get("STEPH_MAC_VOICE", "Thomas"), text]
    if shutil.which("spd-say"):
        return ["spd-say", "-w", "-l", "fr", text]
    if shutil.which("espeak-ng"):
        return ["espeak-ng", "-v", "fr", text]
    return None


def popen_quiet(cmd: list[str], stdin=None) -> subprocess.Popen:
    return subprocess.Popen(cmd, stdin=stdin, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
