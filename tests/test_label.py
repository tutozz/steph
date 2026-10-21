"""Tests of the pure parts of bench/matrix/finetune/label.py (K2 : English labels).

No server call here: only TRAIN_SYSTEM selection by language. label.py's
network path (query/judge against a running llama-server) is exercised by
hand on the GPU machines.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix" / "finetune"))

import pytest

from label import TRAIN_SYSTEM, TRAIN_SYSTEM_EN, build_messages, train_system_for

# The French prompt must stay byte-identical to what shipped before K2: any
# drift here silently changes every future FR-labeled example.
FR_BYTES = (
    "Tu lis la sortie d'une commande de terminal et tu dis à voix haute l'essentiel, en français. "
    "Réponds par une seule ligne courte, 15 mots au plus : d'abord le résultat, puis un détail utile. "
    "Recopie les noms et les nombres exactement comme dans la sortie. Si une information n'est pas "
    "écrite dans la sortie, ne la donne pas : n'invente jamais."
)


def test_default_fr_train_system_is_byte_identical_to_before():
    assert TRAIN_SYSTEM == FR_BYTES
    assert TRAIN_SYSTEM.encode("utf-8") == FR_BYTES.encode("utf-8")


def test_train_system_for_fr_returns_the_original_constant():
    assert train_system_for("fr") is TRAIN_SYSTEM


def test_train_system_for_en_returns_the_english_prompt():
    result = train_system_for("en")
    assert result == TRAIN_SYSTEM_EN
    assert "never invent" in result.lower()
    assert "français" not in result.lower()


def test_train_system_for_en_is_short_enough_for_the_training_budget():
    assert len(train_system_for("en").split()) <= 80


def test_train_system_for_unknown_lang_raises():
    with pytest.raises(ValueError):
        train_system_for("de")


EN_DF_REC = {
    "cmd": "df -h",
    "exit": 0,
    "duration": 0.1,
    "output": (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/root       953G  268G  685G  29% /\n"
    ),
}


def test_build_messages_defaults_to_french_digest_and_prompt():
    msgs = build_messages(EN_DF_REC, 1500)
    assert msgs[1]["content"].startswith("Commande :")


def test_build_messages_en_routes_digest_and_prompt_to_english():
    """K2 bug: build_messages never forwarded a language to digest()/summary_messages(),
    so --lang en still produced French user messages ("Commande :", "libres sur")."""
    msgs = build_messages(EN_DF_REC, 1500, language="en")
    user = msgs[1]["content"]
    assert user.startswith("Command:")
    assert "Commande :" not in user
    assert "libres sur" not in user
    assert "free of" in user
