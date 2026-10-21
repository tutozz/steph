"""Synthèse vocale : Piper en processus (voix préchargée), lecture via audio.py.

- `say(text)` : ajoute une annonce (par défaut, coupe ce qui est en cours).
- `say_stream(pieces)` : lit un flux de tokens LLM phrase par phrase, pour
  commencer à parler avant la fin de la génération.
- Premier son (P19) : le premier segment d'une annonce est court (Piper synthétise un
  segment entier avant d'en rendre le premier octet), le segment suivant se synthétise
  pendant la lecture du précédent, sur un seul lecteur, sans silence de tête ; les
  annonces de statut sont synthétisées d'avance et gardées en mémoire.
- `stop()` : silence immédiat. `repeat()` : relit la dernière annonce.
"""

from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import threading
from array import array
from collections import OrderedDict
from typing import Iterable, Iterator

from . import audio
from .config import Config
from .pronounce import pronounce, to_piper, warm_up
from .strings import t as _t

# T1 : onnxruntime (chargé par Piper) embarque le SDK de télémétrie 1DS de Microsoft et
# journalise un événement à chaque session, sans que rien côté steph ne l'active. La
# variable doit être posée avant sa toute première initialisation (Privacy.md du paquet) :
# ce module est le seul point d'entrée vers Piper/onnxruntime, elle est donc posée ici,
# à l'import, avant que _load_voice() ne déclenche cette première initialisation.
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

SENTENCE_END = re.compile(r"([.!?…]\s|\n)")
_CLAUSE_END = re.compile(r"[,;:](?=\s)")

# Coût de synthèse du premier segment : Piper met ~5 ms par caractère sur l'i5-7200U, un
# chiffre compte pour quatre (« 192 » se dit « cent quatre-vingt-douze »). 40 tient le
# premier segment sous 0,2 s de synthèse (mesure P19).
FIRST_SEGMENT_BUDGET = 40
# Seuls les segments courts reviennent assez souvent pour valoir une place en cache.
CACHE_MAX_CHARS = 40
CACHE_SIZE = 64
# Piper ouvre chaque segment par 40 à 160 ms de silence : on en garde juste de quoi ne
# pas rogner l'attaque de la première consonne.
SILENCE_LEVEL = 300
SILENCE_MARGIN_S = 0.02
PREWARM_CODES = (1, 2, 127)


def speech_cost(text: str) -> int:
    return sum(4 if c.isdigit() else 1 for c in text)


def split_first(text: str, budget: int = FIRST_SEGMENT_BUDGET) -> tuple[str, str]:
    """Coupe un premier segment trop long à synthétiser : à la première ponctuation
    faible dans le budget, sinon à la dernière espace dans le budget, sinon à la
    première espace. `head + tail == text` ; tail vide si rien n'est coupé."""
    if speech_cost(text.strip()) <= budget:
        return text, ""
    cost, limit = 0, len(text)
    for i, c in enumerate(text):
        cost += 4 if c.isdigit() else 1
        if cost > budget:
            limit = i
            break
    cut = next((m.end() for m in _CLAUSE_END.finditer(text, 0, limit) if len(text[:m.start()].strip()) >= 2), None)
    if cut is None:
        space = text.rfind(" ", 0, limit + 1)
        if space > 0 and text[:space].strip():
            cut = space
        else:
            space = text.find(" ", limit)
            cut = space if space > 0 else None
    if cut is None or not text[cut:].strip():
        return text, ""
    return text[:cut], text[cut:]


def trim_leading_silence(pcm: bytes, rate: int) -> bytes:
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    first = next((i for i, v in enumerate(samples) if abs(v) > SILENCE_LEVEL), None)
    if first is None:
        return pcm
    start = max(0, first - int(rate * SILENCE_MARGIN_S))
    return pcm[2 * start:]


def prewarm_phrases(language: str) -> list[str]:
    """Annonces de statut dites telles quelles en premier segment, à synthétiser d'avance."""
    phrases = [_t(language, k) for k in ("narrator.status_success", "ok", "interrupted",
                                          "resolve.failed", "no_output", "qa_wait")]
    phrases += [_t(language, "narrator.status_failed").format(code=c) for c in PREWARM_CODES]
    head = _t(language, "error_code").split("{say}")[0]
    phrases += [head.format(code=c) for c in PREWARM_CODES]
    return [p.strip() for p in phrases]


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
    return pronounce(t.strip())


class _Utterance:
    def __init__(self, pieces: Iterable[str], on_done=None, force: bool = False):
        self.pieces = pieces
        self.text = ""
        self.on_done = on_done
        self.force = force  # parle même si tts_enabled est faux (menu)


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
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._cache_ctx: tuple | None = None
        self._cache_lock = threading.Lock()  # prérendu (thread tts) et synthèse (tts-synth)
        self._prewarmed: set[tuple] = set()
        self._thread = threading.Thread(target=self._run, daemon=True, name="tts")
        self._load_voice()
        self._thread.start()

    def _load_voice(self) -> None:
        if not self.enabled:
            return
        try:
            from piper import PiperVoice, SynthesisConfig

            import onnxruntime
            onnxruntime.disable_telemetry_events()  # défense en profondeur : voir ORT_DISABLE_TELEMETRY plus haut

            self.voice = PiperVoice.load(self.cfg.voice)
            self.rate = self.voice.config.sample_rate
            self.syn = SynthesisConfig(length_scale=1.0 / max(0.5, self.cfg.speech_rate))
            warm_up()
        except Exception:
            self.voice = None  # repli : voix du système

    # ---------------------------------------------------------------- API
    def say(self, text: str, interrupt: bool = True, on_done=None, force: bool = False) -> None:
        text = text.strip()
        if not text:
            return
        self.say_stream([text], interrupt=interrupt, on_done=on_done, force=force)

    def say_stream(self, pieces: Iterable[str], interrupt: bool = True, on_done=None, force: bool = False) -> None:
        """`force=True` : parle même si `tts_enabled` est faux (menu, qui doit
        toujours être audible ; `tts_enabled` ne coupe que la narration)."""
        if interrupt:
            self.stop()
        self._q.put(_Utterance(pieces, on_done, force=force))

    def stop(self) -> None:
        with self._lock:
            self._gen += 1
            while True:
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
            self._kill_player()

    def stop_all(self) -> None:
        """Touche « couper la parole » : ici, une seule fenêtre parle, c'est stop()."""
        self.stop()

    def note_input(self) -> None:
        """Frappe dans la fenêtre : utile seulement à la voix partagée (voice_client)."""

    def repeat(self) -> None:
        if self.last_text:
            self.say(self.last_text)

    def reload_voice(self, voice_path: str) -> None:
        """Recharge la voix à chaud (menu : cycle des voix disponibles). Ne fait
        rien de plus que relancer le chargement déjà fait à la construction :
        sans effet si la synthèse est coupée (`tts_enabled`)."""
        self.cfg.voice = voice_path
        self._load_voice()

    def can_speak(self) -> bool:
        """Faux si aucun son ne peut sortir : ni lecteur pour Piper, ni voix du système."""
        if self.voice is not None:
            return bool(audio.stream_player_cmd(self.rate) or audio.file_player_cmd("x.wav"))
        return audio.system_voice_cmd("x") is not None

    def set_rate(self, rate: float) -> None:
        """Applique un nouveau débit sans recharger le modèle de voix."""
        self.cfg.speech_rate = rate
        if self.voice is not None:
            from piper import SynthesisConfig

            self.syn = SynthesisConfig(length_scale=1.0 / max(0.5, rate))

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
        first = True  # le premier segment d'une annonce doit se synthétiser vite
        for piece in self._pump(pieces, gen):
            if gen != self._gen:
                return
            buf += piece
            while True:
                m = SENTENCE_END.search(buf)
                if first and (m or speech_cost(buf) > FIRST_SEGMENT_BUDGET):
                    first = False
                    head, tail = split_first(buf[:m.end()] if m else buf)
                    if tail:
                        yield head
                        buf = buf[len(head):]
                        continue
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

    def _next_utterance(self) -> _Utterance | None:
        """Attend la prochaine annonce ; en attendant, synthétise d'avance les annonces
        de statut, une à la fois pour ne retarder une annonce que d'un segment court."""
        self._prewarm_idle(lambda: not self._q.empty())
        return self._q.get()

    def _prewarm_idle(self, busy, extra: Iterable[str] = ()) -> None:
        """Synthétise d'avance les phrases pas encore faites, en rendant la main dès que
        `busy()` : une annonce n'attend jamais plus d'un segment court."""
        if self.voice is None or not self.enabled:
            return
        ctx = self._cache_context()
        for phrase in [*prewarm_phrases(self.cfg.language), *extra]:
            if (ctx, phrase) in self._prewarmed:
                continue
            if busy() or self._cache_context() != ctx:
                return
            try:
                self._pcm(to_piper(normalize_for_speech(phrase)))
            except Exception:
                return
            self._prewarmed.add((ctx, phrase))

    def _run(self) -> None:
        while True:
            utt = self._next_utterance()
            if utt is None:
                return
            gen = self._gen
            spoken: list[str] = []
            self.speaking.set()
            try:
                self._speak_all(self._segments(utt, gen, spoken), gen)
            except Exception:
                pass
            finally:
                self.speaking.clear()
            self._finish_utterance(utt, spoken)

    def _segments(self, utt: _Utterance, gen: int, spoken: list[str]) -> Iterator[str]:
        """Segments à dire, déjà normalisés ; `spoken` reçoit le texte, même voix coupée."""
        for sentence in self._sentences(utt.pieces, gen):
            if gen != self._gen:
                return
            s = sentence.strip()
            if not s:
                continue
            spoken.append(s)
            self._journal(s)
            if self.enabled or utt.force:
                yield normalize_for_speech(s)

    def _finish_utterance(self, utt: _Utterance, spoken: list[str]) -> None:
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

    def _speak_all(self, texts: Iterator[str], gen: int) -> None:
        stream_cmd = audio.stream_player_cmd(self.rate) if self.voice is not None else None
        if stream_cmd:
            self._play_pipelined(stream_cmd, (to_piper(t) for t in texts), gen)
        else:
            for text in texts:
                if gen != self._gen:
                    return
                self._speak_one(text, gen)

    def _speak_one(self, text: str, gen: int) -> None:
        if not text:
            return
        if self.voice is None:
            cmd = audio.system_voice_cmd(text)
            if not cmd:
                return
            with self._lock:
                if gen != self._gen:
                    return
                self._proc = audio.popen_quiet(cmd)
            self._proc.wait()
            return
        text = to_piper(text)
        stream_cmd = audio.stream_player_cmd(self.rate)
        if stream_cmd:
            self._play_pipelined(stream_cmd, iter([text]), gen)
        else:
            self._play_file(text, gen)

    # ------------------------------------------------------------ audio Piper
    def _cache_context(self) -> tuple:
        return (self.cfg.voice, self.cfg.speech_rate, self.cfg.language)

    def _pcm(self, text: str) -> bytes:
        """Audio d'un segment (texte déjà passé par to_piper), sans silence de tête.
        Les segments courts restent en cache tant que voix, débit et langue ne changent pas."""
        ctx = self._cache_context()
        with self._cache_lock:
            if ctx != self._cache_ctx:
                self._cache.clear()
                self._cache_ctx = ctx
            pcm = self._cache.get(text)
            if pcm is not None:
                self._cache.move_to_end(text)
                return pcm
        pcm = b"".join(ch.audio_int16_bytes for ch in self.voice.synthesize(text, syn_config=self.syn))
        pcm = trim_leading_silence(pcm, self.rate)
        with self._cache_lock:
            if len(text) <= CACHE_MAX_CHARS and self._cache_context() == self._cache_ctx == ctx:
                self._cache[text] = pcm
                while len(self._cache) > CACHE_SIZE:
                    self._cache.popitem(last=False)
        return pcm

    def _play_pipelined(self, cmd: list[str], texts: Iterator[str], gen: int) -> None:
        """Un seul lecteur pour toute l'annonce ; le segment suivant se synthétise dans
        un autre thread pendant que le précédent joue (l'écriture bloque au rythme du son)."""
        ready: queue.Queue = queue.Queue()
        END = object()

        def synthesize():
            try:
                for text in texts:
                    if gen != self._gen:
                        break
                    pcm = self._pcm(text) if text else b""
                    if pcm:
                        ready.put(pcm)
            except Exception:
                pass
            finally:
                ready.put(END)

        threading.Thread(target=synthesize, daemon=True, name="tts-synth").start()
        proc = None
        try:
            while gen == self._gen:
                try:
                    pcm = ready.get(timeout=0.05)
                except queue.Empty:
                    continue
                if pcm is END:
                    break
                if proc is None:
                    with self._lock:
                        if gen != self._gen:
                            break
                        proc = self._proc = audio.popen_quiet(cmd, stdin=subprocess.PIPE)
                proc.stdin.write(pcm)
                proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass
        if proc is not None:
            try:
                proc.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass
            proc.wait()

    def _play_file(self, text: str, gen: int) -> None:
        pcm = self._pcm(text)
        if gen != self._gen or not pcm:
            return
        path = audio.write_wav(pcm, self.rate)
        try:
            cmd = audio.file_player_cmd(path)
            if not cmd:
                return
            with self._lock:
                if gen != self._gen:
                    return
                self._proc = audio.popen_quiet(cmd)
            self._proc.wait()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
