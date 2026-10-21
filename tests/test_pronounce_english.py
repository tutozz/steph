"""Étape anglaise : mots anglais prononcés à l'anglaise par la voix française de Piper."""

import re

import pytest

from steph.config import DATA_DIR, Config
from steph.pronounce import UNTRAINED_PHONEMES, to_piper
from steph.tts import Speaker

REAL_VOICE = DATA_DIR / "voices" / "fr_FR-siwis-medium.onnx"
BLOCK = re.compile(r"\[\[(.*?)\]\]")


def blocks(text: str) -> list[str]:
    return BLOCK.findall(text)


@pytest.mark.parametrize("word", ["build", "run", "title", "refused", "grep", "stdout"])
def test_english_words_become_phonemes(word):
    out = to_piper(f"Le mot {word} ici.")
    assert out.startswith("Le mot [[") and out.endswith("]] ici.")
    assert len(blocks(out)) == 1


def test_typescript_is_said_the_english_way():
    (ipa,) = blocks(to_piper("Erreur TypeScript : la propriété titel n'existe pas."))
    assert "aj" in ipa  # « taïpe », pas « tipe »


@pytest.mark.parametrize("text", [
    "Le fichier a été supprimé en 3 secondes.",
    "Mise à jour des paquets : 35 pour cent.",
    "Question : souhaitez-vous continuer ? Oui ou non.",
    "Une table, un type, un service, un port, un message.",
    "Erreur : la propriété titel n'existe pas.",
])
def test_french_text_unchanged(text):
    assert to_piper(text) == text


@pytest.mark.parametrize("text", ["N P M", "S S H prêt", "guite hub", "P C I express"])
def test_output_of_lexicon_and_spelled_letters_untouched(text):
    assert to_piper(text) == text


@pytest.mark.parametrize("text", ["vim9", "script.sh", "2b:00.0", "v1.2.3"])
def test_tokens_with_digits_or_dots_untouched(text):
    assert to_piper(f"voir {text} ici") == f"voir {text} ici"


@pytest.mark.parametrize("ident", ["useState", "getElementById", "TypeScript"])
def test_camel_case_identifiers_are_english(ident):
    assert len(blocks(to_piper(f"appel {ident} ici"))) == 1


def test_only_phonemes_the_french_voice_learned():
    words = ("build run push title refused grep stdout thread the upgrade container string "
             "warning branch feature merge docker python node common error undefined install")
    for ipa in blocks(to_piper(words)):
        assert not set(ipa) & UNTRAINED_PHONEMES, ipa


def test_idempotent():
    once = to_piper("npm run build")
    assert to_piper(once) == once


@pytest.mark.skipif(not REAL_VOICE.exists(), reason="voix Piper absente")
def test_piper_reads_the_blocks():
    from piper import PiperVoice

    voice = PiperVoice.load(str(REAL_VOICE))
    audio = b"".join(c.audio_int16_bytes for c in voice.synthesize(to_piper("Le build a échoué.")))
    assert len(audio) > 10_000


def test_system_voice_fallback_gets_plain_text(monkeypatch):
    from steph import audio

    cfg = Config()
    cfg.tts_enabled = False
    sp = Speaker(cfg)
    try:
        sent = []
        monkeypatch.setattr(audio, "system_voice_cmd", lambda text: sent.append(text) or None)
        sp._speak_one("npm run build", sp._gen)
        assert sent == ["npm run build"]
    finally:
        sp.close()


@pytest.mark.skipif(not REAL_VOICE.exists(), reason="voix Piper absente")
def test_piper_path_gets_phonemes(monkeypatch):
    cfg = Config()
    cfg.voice = str(REAL_VOICE)
    sp = Speaker(cfg)
    try:
        assert sp.voice is not None
        seen = []
        monkeypatch.setattr(sp, "_play_file", lambda text, gen: seen.append(text))
        from steph import audio

        monkeypatch.setattr(audio, "stream_player_cmd", lambda rate: None)
        sp._speak_one("npm run build", sp._gen)
        assert seen and "[[" in seen[0]
    finally:
        sp.close()


def test_no_doubled_r_after_r_colored_vowel():
    (ipa,) = blocks(to_piper("Intel Corporation"))[1:]
    assert "ʁʁ" not in ipa


def test_word_next_to_single_bracket_is_converted():
    out = to_piper("[GeForce RTX 3060 Lite Hash Rate]")
    assert out.endswith("]]]") and len(blocks(out)) >= 2


def test_existing_phoneme_blocks_untouched():
    text = "avant [[ bˈild ]] après"
    assert to_piper(text) == text


@pytest.mark.parametrize("raw, spoken", [("pwd", "P W D"), ("ls", "L S"), ("cd", "C D")])
def test_lowercase_abbreviations_spelled_with_french_letters(raw, spoken):
    assert to_piper(f"Commande {raw} lancée.") == f"Commande {spoken} lancée."


def test_palatal_mark_removed():
    assert "ʲ" not in "".join(blocks(to_piper("React")))


@pytest.mark.parametrize("text", [
    "La rate est un organe situé sous les côtes.",
    "Le fichier est en cache depuis hier.",
    "Une file d'attente se forme à la date prévue.",
])
def test_french_words_that_are_also_english_stay_french(text):
    assert to_piper(text) == text


@pytest.mark.parametrize("text, word", [
    ("GeForce RTX 3060 laïte ache Rate", "Rate"),
    ("le rate limite est atteint", "rate"),
])
def test_ambiguous_word_is_english_in_tech_context(text, word):
    assert word not in to_piper(text).split()


def test_start_keeps_its_a_sound():
    (ipa,) = blocks(to_piper("Le service restart a réussi."))
    assert "aʁ" in ipa and "ɔʁ" not in ipa


def test_docker_keeps_its_o_sound():
    (ipa,) = blocks(to_piper("Le conteneur docker tourne."))
    assert "ɔ" in ipa


@pytest.mark.parametrize("word", ["sudo", "push"])
def test_words_whisper_hears_better_in_french_stay_french(word):
    assert to_piper(f"Relancez avec {word}.") == f"Relancez avec {word}."


@pytest.mark.skipif(not REAL_VOICE.exists(), reason="voix Piper absente")
def test_speaker_warms_up_the_english_step(monkeypatch):
    import steph.pronounce as pr

    monkeypatch.setattr(pr, "_english_words", None)
    monkeypatch.setattr(pr, "_phonemizer", None)
    cfg = Config()
    cfg.voice = str(REAL_VOICE)
    sp = Speaker(cfg)
    try:
        assert pr._english_words is not None and pr._phonemizer is not None
    finally:
        sp.close()


def _broken():
    raise OSError("liste de mots absente")


def test_failure_of_english_step_keeps_plain_text(monkeypatch):
    import steph.pronounce as pr

    monkeypatch.setattr(pr, "_load_english_words", _broken)
    assert pr.to_piper("npm run build") == "npm run build"
    pr.warm_up()  # ne lève rien


@pytest.mark.skipif(not REAL_VOICE.exists(), reason="voix Piper absente")
def test_failure_of_english_step_keeps_piper_voice(monkeypatch):
    import steph.pronounce as pr

    monkeypatch.setattr(pr, "_load_english_words", _broken)
    cfg = Config()
    cfg.voice = str(REAL_VOICE)
    sp = Speaker(cfg)
    try:
        assert sp.voice is not None
    finally:
        sp.close()
