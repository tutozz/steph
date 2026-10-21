"""P19 : premier son rapide. Découpage du premier segment, audio en cache, lecture en flux
(synthèse du segment suivant pendant la lecture du précédent), silence de tête retiré."""

import struct
import threading
import time
from types import SimpleNamespace

import pytest

from steph import audio, tts
from steph.config import Config
from steph.pronounce import to_piper
from steph.tts import (FIRST_SEGMENT_BUDGET, Speaker, normalize_for_speech, prewarm_phrases,
                       speech_cost, split_first, trim_leading_silence)

RATE = 22050


# ---------------------------------------------------------------- découpage

def test_short_sentence_is_not_split():
    assert split_first("Succès.") == ("Succès.", "")


def test_long_sentence_is_cut_at_first_clause_punctuation():
    text = "37 éléments affichés : abrt, adjtime, aliases, bash.bashrc, bindresvport.blacklist."
    head, tail = split_first(text)
    assert head == "37 éléments affichés :"
    assert tail.strip().startswith("abrt")


def test_error_code_head_is_the_cached_phrase():
    head, _ = split_first("Erreur 1 : cat: /nonexistent/file.txt: Aucun fichier ou dossier de ce nom")
    assert head == "Erreur 1 :"


def test_english_error_code_head_is_the_cached_phrase():
    head, _ = split_first("Error 1: cat: /nonexistent/file.txt: No such file or directory")
    assert head == "Error 1:"


def test_digits_cost_more_than_letters():
    letters = "abcdefghij abcdefghij abcdefghij"
    digits = "1234567890 1234567890 1234567890"
    assert split_first(letters) == (letters, "")
    assert split_first(digits)[1]


def test_without_punctuation_cut_at_a_space_within_budget():
    text = ("Linux devbox 7.0.9-202.fc44.x86_64 #1 SMP PREEMPT_DYNAMIC Mon May 18 22:33:24 UTC 2026 "
            "x86_64 GNU/Linux")
    head, tail = split_first(text)
    assert tail
    assert tail.startswith(" ")  # coupé sur une espace, jamais dans un mot
    assert speech_cost(head) <= FIRST_SEGMENT_BUDGET


def test_single_long_word_is_never_broken():
    text = "/very/long/path/without/any/space/at/all/in/it/really/long.txt"
    assert split_first(text) == (text, "")


@pytest.mark.parametrize("text", [
    "Succès.",
    "racine : 685G libres sur 953G, 29 %. boot : 284M libres sur 974M, 69 %.",
    "wlp0s20f3 192.168.1.20, tailscale0 100.64.0.10, tun0 10.9.0.2.",
    "Header.tsx ligne 42 : Property titel does not exist on type Props.",
])
def test_split_never_loses_text(text):
    head, tail = split_first(text)
    assert head + tail == text


def _segments(sp: Speaker, pieces) -> list[str]:
    return [s.strip() for s in sp._sentences(pieces, sp._gen) if s.strip()]


def test_only_the_first_segment_of_an_utterance_is_split():
    sp = Speaker(Config(tts_enabled=False))
    try:
        later = "Deuxième phrase, avec des virgules, assez longue pour dépasser le budget."
        segs = _segments(sp, [f"Erreur 1 : cat: /nonexistent/file.txt: aucun fichier de ce nom. {later}"])
        assert segs[0] == "Erreur 1 :"
        assert segs[-1] == later
    finally:
        sp.close()


def test_first_segment_is_split_while_tokens_stream_in():
    sp = Speaker(Config(tts_enabled=False))
    try:
        words = "Linux devbox 7.0.9-202.fc44.x86_64 #1 SMP PREEMPT_DYNAMIC Mon May 18 22:33:24 UTC 2026".split()
        segs = _segments(sp, iter(w + " " for w in words))
        assert len(segs) >= 2
        assert speech_cost(segs[0]) <= FIRST_SEGMENT_BUDGET
        assert " ".join(segs) == " ".join(words)
    finally:
        sp.close()


# ---------------------------------------------------------------- silence de tête

def _pcm(*samples: int) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def test_trim_removes_leading_silence_but_keeps_a_short_margin():
    silence = _pcm(*([0] * int(RATE * 0.2)))
    speech = _pcm(*([9000] * 500))
    out = trim_leading_silence(silence + speech, RATE)
    assert out.endswith(speech)
    lead_s = (len(out) - len(speech)) / 2 / RATE
    assert 0 < lead_s <= 0.03


def test_trim_keeps_trailing_silence():
    speech, silence = _pcm(*([9000] * 500)), _pcm(*([0] * 3000))
    assert trim_leading_silence(speech + silence, RATE) == speech + silence


def test_trim_leaves_silent_audio_untouched():
    silence = _pcm(*([0] * 3000))
    assert trim_leading_silence(silence, RATE) == silence


# ---------------------------------------------------------------- doubles

class FakeVoice:
    """Voix Piper factice : un échantillon distinct par appel, durée proportionnelle au texte."""

    def __init__(self, delay: float = 0.0, lead_silence: int = 0):
        self.config = SimpleNamespace(sample_rate=RATE)
        self.calls: list[str] = []
        self.starts: list[float] = []
        self.delay = delay
        self.lead = lead_silence

    def synthesize(self, text, syn_config=None):
        self.starts.append(time.monotonic())
        self.calls.append(text)
        time.sleep(self.delay)
        level = 5000 + len(self.calls)
        yield SimpleNamespace(audio_int16_bytes=_pcm(*([0] * self.lead)) + _pcm(*([level] * (50 * len(text)))))


class FakePlayer:
    """Lecteur factice : chaque écriture « joue » pendant `play_s` secondes."""

    def __init__(self, log: list, play_s: float = 0.0):
        self.stdin = self
        self.log = log
        self.play_s = play_s
        self.killed = self.closed = False

    def write(self, data):
        if self.killed:
            raise BrokenPipeError
        start = time.monotonic()
        time.sleep(self.play_s)
        self.log.append((self, data, start, time.monotonic()))

    def flush(self):
        pass

    def close(self):
        self.closed = True

    def poll(self):
        return 0 if (self.closed or self.killed) else None

    def wait(self):
        return 0

    def kill(self):
        self.killed = True


def make_speaker(monkeypatch, voice: FakeVoice, play_s: float = 0.0, prewarm: bool = False):
    if not prewarm:
        monkeypatch.setattr(tts, "prewarm_phrases", lambda language: [])
    log: list = []
    players: list = []

    def popen(cmd, stdin=None):
        p = FakePlayer(log, play_s)
        players.append(p)
        return p

    monkeypatch.setattr(audio, "stream_player_cmd", lambda rate: ["fake-player"])
    monkeypatch.setattr(audio, "popen_quiet", popen)
    sp = Speaker(Config(tts_enabled=False))
    sp.voice, sp.syn, sp.enabled = voice, None, True
    return sp, log, players


def wait_done(sp: Speaker, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    time.sleep(0.05)
    while (sp.speaking.is_set() or not sp._q.empty()) and time.time() < deadline:
        time.sleep(0.01)


def piper_key(text: str) -> str:
    return to_piper(normalize_for_speech(text))


# ---------------------------------------------------------------- cache

def test_short_segment_is_synthesized_once(monkeypatch):
    voice = FakeVoice()
    sp, _, _ = make_speaker(monkeypatch, voice)
    try:
        first = sp._pcm("Succès.")
        assert sp._pcm("Succès.") == first
        assert voice.calls == ["Succès."]
    finally:
        sp.close()


def test_long_segment_is_not_cached(monkeypatch):
    voice = FakeVoice()
    sp, _, _ = make_speaker(monkeypatch, voice)
    try:
        text = "Une phrase bien plus longue que les phrases fixes du cache audio."
        sp._pcm(text)
        sp._pcm(text)
        assert voice.calls == [text, text]
    finally:
        sp.close()


@pytest.mark.parametrize("change", [
    lambda sp: sp.set_rate(1.6),
    lambda sp: setattr(sp.cfg, "voice", "/autre/voix.onnx"),
    lambda sp: setattr(sp.cfg, "language", "en"),
])
def test_cache_is_invalidated_when_voice_rate_or_language_change(monkeypatch, change):
    voice = FakeVoice()
    sp, _, _ = make_speaker(monkeypatch, voice)
    try:
        sp._pcm("OK.")
        change(sp)
        sp._pcm("OK.")
        assert voice.calls == ["OK.", "OK."]
    finally:
        sp.close()


def test_cached_audio_has_no_leading_silence(monkeypatch):
    voice = FakeVoice(lead_silence=int(RATE * 0.16))
    sp, _, _ = make_speaker(monkeypatch, voice)
    try:
        pcm = sp._pcm("Succès.")
        assert len(pcm) / 2 / RATE < 0.03 + 50 * len("Succès.") / RATE
    finally:
        sp.close()


@pytest.mark.parametrize("language, expected", [
    ("fr", {"Succès.", "OK.", "Interrompu.", "Échec.", "Échec, code 1.", "Erreur 1 :"}),
    ("en", {"Success.", "OK.", "Interrupted.", "Failed.", "Failed, code 1.", "Error 1:"}),
])
def test_prewarm_phrases_cover_status_announcements(language, expected):
    assert expected <= set(prewarm_phrases(language))


def test_idle_speaker_prewarms_status_phrases(monkeypatch):
    voice = FakeVoice()
    sp, _, _ = make_speaker(monkeypatch, voice, prewarm=True)
    try:
        sp.say("Bonjour.")
        wait_done(sp)
        deadline = time.time() + 3
        while piper_key("Échec, code 1.") not in sp._cache and time.time() < deadline:
            time.sleep(0.01)
        n = len(voice.calls)
        sp._pcm(piper_key("Succès."))
        sp._pcm(piper_key("Échec, code 1."))
        assert len(voice.calls) == n  # déjà en cache : aucune synthèse
    finally:
        sp.close()


# ---------------------------------------------------------------- lecture en flux

def test_segments_play_in_order_on_a_single_player(monkeypatch):
    voice = FakeVoice()
    sp, log, players = make_speaker(monkeypatch, voice)
    try:
        sp.say("Erreur 1 : cat: /nonexistent/file.txt: aucun fichier. Deuxième phrase. Troisième phrase.")
        wait_done(sp)
        assert len(players) == 1
        levels = [struct.unpack_from("<h", data)[0] for _, data, _, _ in log]
        assert levels == sorted(levels) and len(levels) == len(voice.calls) == 4
        assert players[0].closed
    finally:
        sp.close()


def test_next_segment_is_synthesized_while_previous_plays(monkeypatch):
    voice = FakeVoice(delay=0.02)
    sp, log, _ = make_speaker(monkeypatch, voice, play_s=0.3)
    try:
        sp.say("Première phrase. Deuxième phrase.")
        wait_done(sp)
        first_write_end = log[0][3]
        assert voice.starts[1] < first_write_end
    finally:
        sp.close()


def test_spoken_text_is_unchanged_by_the_split(monkeypatch):
    voice = FakeVoice()
    sp, _, _ = make_speaker(monkeypatch, voice)
    try:
        text = "37 éléments affichés : abrt, adjtime, aliases, bash.bashrc, bindresvport.blacklist."
        got = []
        sp.say(text, on_done=got.append)
        wait_done(sp)
        assert got == [text]
        assert sp.last_text == text
    finally:
        sp.close()


def test_stop_kills_the_player_and_the_next_utterance_plays(monkeypatch):
    voice = FakeVoice(delay=0.01)
    sp, log, players = make_speaker(monkeypatch, voice, play_s=0.5)
    try:
        sp.say("Une. Deux. Trois. Quatre. Cinq.")
        time.sleep(0.2)
        t0 = time.monotonic()
        sp.say("Suite.")
        wait_done(sp)
        assert players[0].killed
        assert len(players) == 2
        assert log[-1][0] is players[1]
        assert time.monotonic() - t0 < 1.5
    finally:
        sp.close()


def test_muted_narration_does_not_synthesize(monkeypatch):
    voice = FakeVoice()
    sp, _, players = make_speaker(monkeypatch, voice)
    try:
        sp.enabled = False
        sp.say("Rien à dire.")
        wait_done(sp)
        assert voice.calls == [] and players == []
        assert sp.last_text == "Rien à dire."
    finally:
        sp.close()


def test_segments_are_journaled_in_order(tmp_path, monkeypatch):
    voice = FakeVoice()
    sp, _, _ = make_speaker(monkeypatch, voice)
    try:
        sp.cfg.speech_log = str(tmp_path / "speech.log")
        sp.say("Erreur 1 : cat: /nonexistent/file.txt: aucun fichier. Fin.")
        wait_done(sp)
        lines = [l.split("\t", 1)[1] for l in (tmp_path / "speech.log").read_text().splitlines()]
        assert lines == ["Erreur 1 :", "cat: /nonexistent/file.txt: aucun fichier.", "Fin."]
    finally:
        sp.close()


def test_threads_do_not_leak_after_many_utterances(monkeypatch):
    voice = FakeVoice()
    sp, _, _ = make_speaker(monkeypatch, voice)
    try:
        before = threading.active_count()
        for i in range(20):
            sp.say(f"Phrase {i}. Encore.", interrupt=False)
        wait_done(sp)
        time.sleep(0.2)
        assert threading.active_count() <= before + 2
    finally:
        sp.close()
