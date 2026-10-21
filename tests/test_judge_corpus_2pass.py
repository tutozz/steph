"""Tests of the pure parts of bench/matrix/finetune/judge_corpus_2pass.py (K2).

No server call here: consensus() and category() are pure. The network path (judge_pass /
call_judge against a running llama-server) is exercised by hand on rtx3060, revalidated
6/6 (FR) + 4/4 (EN control) via judge_validate.py before every corpus-label judging run.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix" / "finetune"))

from judge_corpus_2pass import category, consensus, digest  # noqa: E402


def test_consensus_invention_requires_both_passes_to_agree():
    assert consensus("invention", "invention") == "invention"


def test_consensus_single_pass_invention_is_douteux():
    assert consensus("invention", "ok") == "douteux"
    assert consensus("ok", "invention") == "douteux"


def test_consensus_both_ok_is_ok():
    assert consensus("ok", "ok") == "ok"


def test_consensus_erreur_only_when_no_invention_flagged():
    assert consensus("erreur", "ok") == "erreur"
    assert consensus("erreur", "invention") == "douteux"  # une invention confirmée prime


def test_category_line_is_bilingual():
    assert category("ligne 42 inventée") == "ligne"
    assert category("line 42 was invented") == "ligne"


def test_category_status_is_bilingual():
    assert category("statut annoncé à tort") == "statut"
    assert category("wrong success status") == "statut"


def test_category_number_when_no_line_or_status_word():
    assert category("6,6G au lieu de 24G") == "nombre"


def test_category_name_when_dotted_or_hyphenated_token():
    assert category("paquet mod.raop-sink inventé") == "nom"


def test_category_falls_back_to_cause():
    assert category("cause reformulée sans rapport") == "cause"


def test_digest_is_stable_sha256_of_the_user_message():
    row = {"messages": [{"content": "system"}, {"content": "hello"}, {"content": "label"}]}
    assert digest(row) == digest(row)
    assert len(digest(row)) == 64
