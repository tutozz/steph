"""Synthèse vocale : Piper en processus (voix préchargée), lecture via paplay.

- `say(text)` : ajoute une annonce (par défaut, coupe ce qui est en cours).
- `say_stream(pieces)` : lit un flux de tokens LLM phrase par phrase, pour
  commencer à parler avant la fin de la génération.
- `stop()` : silence immédiat. `repeat()` : relit la dernière annonce.
"""

from __future__ import annotations

import queue
import re
import shutil
import subprocess
import threading
from typing import Iterable, Iterator

from .config import Config

SENTENCE_END = re.compile(r"([.!?…]\s|\n)")


def _yes_no(m: re.Match) -> str:
    a, b = m.group(1), m.group(2)
    if a.isupper() and not b.isupper():
        return " oui ou non, oui par défaut"
    if b.isupper() and not a.isupper():
        return " oui ou non, non par défaut"
    return " oui ou non"


def normalize_for_speech(text: str) -> str:
    t = text
    t = re.sub(r"[\[(]\s*([OoYy])\s*/\s*([Nn])\s*[\])]", _yes_no, t)
    t = re.sub(r"https?://([^/\s]+)\S*", r"lien vers \1", t)
    t = re.sub(r"[`*#>|]+", " ", t)
    t = t.replace("_", " ")
    t = re.sub(r"(?<=\w)/(?=\w)", " slash ", t)
    t = re.sub(r"(?<!\w)~/", "dossier perso ", t)
    t = re.sub(r"\s+-{1,2}(?=\w)", " tiret ", t)
    t = t.replace("&&", " puis ").replace("->", " vers ").replace("=>", " vers ")
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


class _Utterance:
    def __init__(self, pieces: Iterable[str], on_done=None):
        self.pieces = pieces
        self.text = ""
        self.on_done = on_done


class Speaker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.enabled = cfg.tts_enabled
        self._q: queue.Queue[_Utterance | None] = queue.Queue()
        self._gen = 0  # incrémenté à chaque stop(): invalide le travail en cours
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self.voice = None
        self.rate = 22050
        self.last_text = ""
        self.history: list[str] = []
        self.speaking = threading.Event()
        self._player = shutil.which("paplay")
        self._thread = threading.Thread(target=self._run, daemon=True, name="tts")
        self._load_voice()
        self._thread.start()

    def _load_voice(self) -> None:
        if not self.enabled:
            return
        try:
            from piper import PiperVoice, SynthesisConfig

            self.voice = PiperVoice.load(self.cfg.voice)
            self.rate = self.voice.config.sample_rate
            self.syn = SynthesisConfig(length_scale=1.0 / max(0.5, self.cfg.speech_rate))
        except Exception:
            self.voice = None  # repli : spd-say

    # ---------------------------------------------------------------- API
    def say(self, text: str, interrupt: bool = True, on_done=None) -> None:
        text = text.strip()
        if not text:
            return
        self.say_stream([text], interrupt=interrupt, on_done=on_done)

    def say_stream(self, pieces: Iterable[str], interrupt: bool = True, on_done=None) -> None:
        if interrupt:
            self.stop()
        self._q.put(_Utterance(pieces, on_done))

    def stop(self) -> None:
        with self._lock:
            self._gen += 1
            while True:
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
            self._kill_player()

    def repeat(self) -> None:
        if self.last_text:
            self.say(self.last_text)

    def close(self) -> None:
        self.stop()
        self._q.put(None)

    # ------------------------------------------------------------ interne
    def _kill_player(self) -> None:
        p = self._proc
        if p and p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass

    def _pump(self, pieces: Iterable[str], gen: int) -> Iterator[str]:
        """Consomme `pieces` (souvent un flux LLM bloquant) dans un thread à part,
        pour que stop() reprenne la main immédiatement."""
        q: queue.Queue = queue.Queue()
        END = object()

        def producer():
            try:
                for p in pieces:
                    q.put(p)
                    if gen != self._gen:
                        break
            except Exception:
                pass
            finally:
                q.put(END)

        threading.Thread(target=producer, daemon=True, name="tts-src").start()
        while gen == self._gen:
            try:
                p = q.get(timeout=0.05)
            except queue.Empty:
                continue
            if p is END:
                return
            yield p

    def _sentences(self, pieces: Iterable[str], gen: int) -> Iterator[str]:
        buf = ""
        for piece in self._pump(pieces, gen):
            if gen != self._gen:
                return
            buf += piece
            while True:
                m = SENTENCE_END.search(buf)
                # coupe aussi sur ponctuation faible si le morceau est déjà long
                if not m and len(buf) > 90:
                    m = re.search(r"[,;:]\s", buf[40:])
                    if m:
                        cut = 40 + m.end()
                        yield buf[:cut]
                        buf = buf[cut:]
                        continue
                if not m:
                    break
                yield buf[:m.end()]
                buf = buf[m.end():]
        if buf.strip() and gen == self._gen:
            yield buf

    def _run(self) -> None:
        while True:
            utt = self._q.get()
            if utt is None:
                return
            gen = self._gen
            spoken = []
            self.speaking.set()
            try:
                for sentence in self._sentences(utt.pieces, gen):
                    if gen != self._gen:
                        break
                    s = sentence.strip()
                    if not s:
                        continue
                    spoken.append(s)
                    self._journal(s)
                    if self.enabled:
                        self._speak_one(normalize_for_speech(s), gen)
            except Exception:
                pass
            finally:
                self.speaking.clear()
            text = " ".join(spoken).strip()
            utt.text = text
            if text:
                self.last_text = text
                self.history.append(text)
                del self.history[:-200]
            if utt.on_done:
                try:
                    utt.on_done(text)
                except Exception:
                    pass

    def _journal(self, s: str) -> None:
        if self.cfg.speech_log:
            import time
            try:
                with open(self.cfg.speech_log, "a") as f:
                    f.write(f"{time.time():.3f}\t{s}\n")
            except OSError:
                pass

    def _speak_one(self, text: str, gen: int) -> None:
        if not text:
            return
        if self.voice is None or not self._player:
            with self._lock:
                if gen != self._gen:
                    return
                self._proc = subprocess.Popen(["spd-say", "-w", "-l", "fr", text],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._proc.wait()
            return
        with self._lock:
            if gen != self._gen:
                return
            self._proc = subprocess.Popen(
                [self._player, "--raw", "--format=s16le", f"--rate={self.rate}", "--channels=1",
                 "--client-name=steph", "--stream-name=voix"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc = self._proc
        try:
            for chunk in self.voice.synthesize(text, syn_config=self.syn):
                if gen != self._gen:
                    break
                proc.stdin.write(chunk.audio_int16_bytes)
                proc.stdin.flush()
            proc.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass
        proc.wait()
