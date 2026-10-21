import pytest

from steph.pronounce import AMBIGUOUS, SPOKEN, pronounce
from steph.tts import normalize_for_speech


# ---------------------------------------------------------------- sigles épelés
@pytest.mark.parametrize("raw, spoken", [
    ("PCI", "P C I,"),
    ("xHCI", "X H C I"),
    ("AMD", "A M D"),
    ("HDMI", "H D M I"),
    ("SSD", "S S D"),
])
def test_spells_known_acronyms(raw, spoken):
    assert pronounce(f"Contrôleur {raw} prêt") == f"Contrôleur {spoken} prêt"


@pytest.mark.parametrize("raw", ["USB", "RTX", "VGA"])
def test_keeps_acronyms_the_voice_reads_well(raw):
    assert pronounce(f"port {raw} libre") == f"port {raw} libre"


def test_pause_comma_not_doubled_before_punctuation():
    assert pronounce("Les périphériques PCI.") == "Les périphériques P C I."
    assert pronounce("PCI") == "P C I"


def test_spells_unknown_short_caps():
    assert pronounce("erreur EIO sur le disque") == "erreur E I O sur le disque"


def test_spells_unknown_caps_without_vowel():
    assert pronounce("module DRM chargé") == "module D R M chargé"


def test_keeps_pronounceable_unknown_caps():
    assert pronounce("code EACCES reçu") == "code EACCES reçu"


def test_keeps_french_words_in_caps():
    assert pronounce("ATTENTION : NON et OUI") == "ATTENTION : NON et OUI"


# ---------------------------------------------------------------- mots et commandes
@pytest.mark.parametrize("word", ["lspci", "git", "dmesg", "chmod", "firmware", "kernel", "commit", "hash"])
def test_lexicon_words_are_respelled(word):
    assert pronounce(f"le {word} ici") == f"le {SPOKEN[word]} ici"


def test_lexicon_is_case_insensitive():
    assert pronounce("GIT") == pronounce("git") == SPOKEN["git"]


def test_hyphenated_package_keeps_lexicon_word():
    assert SPOKEN["firmware"] in pronounce("firmware-misc-nonfree")


# ---------------------------------------------------------------- noms de modèle
@pytest.mark.parametrize("raw, spoken", [
    ("GA106", "G A 106"),
    ("5800X", "5800 X"),
    ("AX210", "A X 210"),
])
def test_splits_model_names(raw, spoken):
    assert pronounce(f"puce {raw} ok") == f"puce {spoken} ok"


def test_lspci_line():
    out = pronounce(normalize_for_speech(
        "2b:00.0 VGA compatible controller: NVIDIA Corporation GA106 [GeForce RTX 3060 Lite Hash Rate]"))
    assert out.startswith("2b:00.0 ")
    assert "VGA" in out and "RTX 3060" in out and "G A 106" in out
    assert f"{SPOKEN['lite']} {SPOKEN['hash']}" in out


# ---------------------------------------------------------------- mots ambigus, contexte
def test_ambiguous_word_respelled_in_tech_context():
    assert pronounce("git pull") == f"{SPOKEN['git']} {AMBIGUOUS['pull']}"
    assert pronounce("Pull request") == f"{AMBIGUOUS['pull']} request"


# ---------------------------------------------------------------- anti sur-correction
@pytest.mark.parametrize("text", [
    "Les commissions sont versées au taux de change.",
    "La rate est un organe situé sous les côtes.",
    "La brebis Dolly était un clone célèbre.",
    "Il a mis son pull et il a raté le train.",
    "Le commit est prêt.".replace("commit", "comité"),
    "Version 1.2.3 installée sur 192.0.2.16.",
    "Le hash vaut 3f9a2c1e et l'UUID 3b1f9c2e-8d4a-4f1b-9c2e-1a2b3c4d5e6f.",
    "Adresse 2b:00.0 et 00:14.0, fichier script.sh.",
    "Erreur 127 : commande introuvable.",
])
def test_french_and_identifiers_untouched(text):
    out = pronounce(text)
    for keep in ("commissions", "change", "rate est", "clone célèbre", "pull et", "raté", "comité",
                 "1.2.3", "192.0.2.16", "3f9a2c1e", "3b1f9c2e-8d4a-4f1b-9c2e-1a2b3c4d5e6f",
                 "2b:00.0", "00:14.0", "script.sh", "127"):
        if keep in text:
            assert keep in out


def test_empty_and_plain_text():
    assert pronounce("") == ""
    assert pronounce("Terminé en une minute.") == "Terminé en une minute."


def test_normalize_for_speech_applies_pronunciation():
    assert normalize_for_speech("lspci") == SPOKEN["lspci"]


def test_bios_acronym_only_in_capitals():
    assert pronounce("Mettez à jour le BIOS.") == "Mettez à jour le baïosse."
    assert pronounce("Des légumes bios au marché.") == "Des légumes bios au marché."
