"""Tests of the bench v3 scorer (score_v3.py): same rule as rescore.score_case, facts per language.

    python3 -m pytest bench/matrix/v3/tools/test_score_v3.py -q

SPDX-License-Identifier: MIT
"""

import json

import pytest

import score_v3

CASE = {
    "id": "v3-tests-9999",
    "task": "summary",
    "family": "tests",
    "max_words": 20,
    "facts": {
        "need": [
            {"id": "failed", "fr": [r"\b2 (tests? )?(en )?echec", r"deux tests?"], "en": [r"\b2 (tests? )?fail", r"two tests?"]},
            {"id": "name", "fr": [r"test_merge"], "en": [r"test_merge"]},
        ],
        "never": [
            {"id": "wrong_total", "fr": [r"\b12 tests?"], "en": [r"\b12 tests?"]},
        ],
    },
}


def test_all_facts_in_french_answer_scores_one():
    assert score_v3.score_answer(CASE, "fr", "2 tests en échec, dont test_merge.") == 1.0


def test_english_answer_uses_english_patterns():
    assert score_v3.score_answer(CASE, "en", "2 tests failed, including test_merge.") == 1.0


def test_french_pattern_not_accepted_for_english_answer():
    assert score_v3.score_answer(CASE, "en", "2 tests en echec, test_merge.") == 0.5


def test_partial_facts_give_fraction():
    assert score_v3.score_answer(CASE, "fr", "Deux tests en échec.") == 0.5


def test_case_never_gives_zero():
    assert score_v3.score_answer(CASE, "fr", "2 tests en échec sur 12 tests, test_merge.") == 0.0


def test_global_never_gives_zero():
    assert score_v3.score_answer(CASE, "en", "**2 tests failed**, test_merge.") == 0.0


def test_too_long_answer_multiplied_by_0_8():
    long = "2 tests failed, test_merge " + " ".join(["word"] * 25)
    assert score_v3.score_answer(CASE, "en", long) == pytest.approx(0.8)


def test_accents_and_case_are_ignored():
    assert score_v3.score_answer(CASE, "fr", "DEUX TESTS ÉCHOUÉS : TEST_MERGE") == 1.0


def test_thinking_block_is_cleaned_before_scoring():
    assert score_v3.score_answer(CASE, "en", "<think>12 tests</think>2 tests failed, test_merge.") == 1.0


def test_spoken_prefix_for_failure_uses_language():
    user = "Command: pytest\nStatus: failed (code 1)\nDuration: 1.0 s; 9 lines printed\nOutput:\n..."
    assert score_v3.spoken("Failed. 2 tests failed.", user, "en") == "Failed, code 1. 2 tests failed."
    user_fr = "Commande : pytest\nStatut : échec (code 1)\nDurée : 1.0 s\nSortie :\n..."
    assert score_v3.spoken("Échec. 2 tests.", user_fr, "fr") == "Échec, code 1. 2 tests."


def test_row_id_splits_case_and_language():
    assert score_v3.parse_row_id("v3-tests-9999@en") == ("v3-tests-9999", "en")


def test_score_file_reports_per_language_and_family(tmp_path):
    rows = [
        {"id": "v3-tests-9999@fr", "fixture": "v3-tests-9999", "kind": "summary", "out": "Deux tests en échec, test_merge."},
        {"id": "v3-tests-9999@en", "fixture": "v3-tests-9999", "kind": "summary", "out": "Two tests failed."},
        {"id": "v3-tests-9998@en", "fixture": "v3-tests-9998", "kind": "summary", "out": None},
    ]
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"label": "x", "rows": rows}))
    res = score_v3.score_file({"v3-tests-9999": CASE, "v3-tests-9998": CASE}, path)
    assert res["quality"] == 75.0
    assert res["fr"] == 100.0 and res["en"] == 50.0
    assert res["by_family"]["tests"] == 75.0
    assert res["n"] == 2 and res["missing"] == 1
    assert res["per_case"] == {"v3-tests-9999@fr": 1.0, "v3-tests-9999@en": 0.5}


# X5 : nombres écrits en lettres, règle générique (paraphrases justes notées à tort sous 100)
NUM_CASE = {
    "id": "v3-x5-9999", "task": "qa", "family": "history-qa", "max_words": 30,
    "facts": {"need": [{"id": "n", "fr": [r"\b36\b"], "en": [r"\b75\b"]}],
              "never": [{"id": "wrong", "fr": [r"\b134\b"], "en": [r"\b320\b"]}]},
}


@pytest.mark.parametrize("text, expected", [
    ("trente-six avertissements", "36 avertissements"),
    ("vingt et un tests", "21 tests"),
    ("soixante-dix-sept", "77"),
    ("quatre-vingt-dix-neuf", "99"),
    ("quatre-vingts", "80"),
    ("deux cent douze fichiers", "212 fichiers"),
    ("mille deux cents", "1200"),
    ("seventy-five times", "75 times"),
    ("one hundred and five lines", "105 lines"),
    ("twenty one", "21"),
    ("three thousand four hundred", "3400"),
    ("neuf virgule un k", "9,1 k"),
    ("six point five", "6.5"),
    ("ligne trois", "ligne 3"),
    ("quarante-quatre pour cent", "44 %"),
    ("cent fichiers", "100 fichiers"),
    ("one hundred ninety-eight point fifty-one point one hundred point eighteen", "198.51.100.18"),
    ("zero point neuf point trois", "0.9.3"),
    ("one hundred percent loss", "100 % loss"),
    ("zero pour cent de perte", "0 % de perte"),
    ("twelve point six five five seconds", "12.655 seconds"),
    ("pid three eight nine eight one", "pid 38981"),
    ("one point two zero", "1.20"),
    ("ligne cinq et un cd", "ligne 5 et un cd"),
    ("three and two", "3 and 2"),
    ("soixante et onze", "71"),
    ("seven hundred three", "703"),
    ("un test en echec", "un test en echec"),
    ("one test failed", "one test failed"),
    ("pointe", "pointe"),
])
def test_number_words_view(text, expected):
    assert score_v3.number_view(text) == expected


def test_number_in_words_meets_a_digit_fact():
    assert score_v3.score_answer(NUM_CASE, "fr", "La compilation a réussi avec trente-six avertissements.") == 1.0
    assert score_v3.score_answer(NUM_CASE, "en", "Omega occurs seventy-five times across thirty-six lines.") == 1.0


def test_number_in_words_still_hits_a_never():
    assert score_v3.score_answer(NUM_CASE, "fr", "Trente-six, ou plutôt cent trente-quatre avertissements.") == 0.0


# X5 : formules d'absence (« introuvable », « not found ») dites autrement, règle générique
ABSENT_CASE = {
    "id": "v3-x5-9998", "task": "summary", "family": "data", "max_words": 20,
    "facts": {"need": [{"id": "name", "fr": [r"\bcustomer\b"], "en": [r"\bcustomer\b"]},
                       {"id": "absent", "fr": [r"introuvable|n.existe pas"], "en": [r"not found|does not exist"]}],
              "never": [{"id": "wrong", "fr": [r"customers (introuvable|absente)"], "en": [r"customers (not found|missing)"]}]},
}


@pytest.mark.parametrize("lang, text", [
    ("en", "Database shop.db lacks the customer table."),
    ("en", "The customer table is absent from shop.db."),
    ("en", "Could not locate the customer table in shop.db."),
    ("en", "The customer table is missing."),
    ("fr", "La table customer est absente de shop.db."),
    ("fr", "La table customer n'a pas été trouvée."),
    ("fr", "On ne trouve pas la table customer."),
    ("fr", "La table customer manque dans shop.db."),
    ("en", "The query found no customer table in shop.db."),
    ("en", "shop.db lacked the customer table."),
    ("en", "shop.db does not have the customer table."),
    ("fr", "Requête arrêtée faute de trouver la table customer."),
    ("fr", "L'erreur signale l'absence de la table customer."),
    ("fr", "La table customer n'est pas présente."),
    ("en", "The customer table is not present."),
    ("en", "The customer table could not be located."),
])
def test_absence_said_otherwise_meets_the_absence_fact(lang, text):
    assert score_v3.score_answer(ABSENT_CASE, lang, text) == 1.0


def test_absence_view_does_not_touch_presence():
    assert score_v3.score_answer(ABSENT_CASE, "en", "The customer table was found in shop.db.") == 0.5
    assert score_v3.score_answer(ABSENT_CASE, "fr", "La table customer a été trouvée.") == 0.5
