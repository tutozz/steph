"""Tests de propose_facts_v3.py : tirage des cas, application d'une proposition, contrôles. Aucun réseau."""

import pytest

import propose_facts_v3 as pf

CASE = {"id": "v3-net-0001", "task": "summary", "family": "network", "max_words": 20,
        "reference": {"fr": "hote1 injoignable, 100 % de perte.", "en": "hote1 unreachable, 100% loss."},
        "facts": {"need": [{"id": "host", "fr": ["hote1"], "en": ["hote1"]},
                           {"id": "loss", "fr": ["100 ?%"], "en": ["100 ?%"]}],
                  "never": [{"id": "ok", "fr": ["\\bsucces\\b"], "en": ["\\bsuccess\\b"]}]}}


def test_add_alternatives_extends_one_fact():
    prop = {"fact_id": "host", "action": "add_alternatives", "fr": ["code 1"], "en": ["code 1"]}
    new = pf.apply_proposal(CASE, prop)
    assert new["facts"]["need"][0]["fr"] == ["hote1", "code 1"]
    assert CASE["facts"]["need"][0]["fr"] == ["hote1"]  # le cas d'origine n'est jamais modifié


def test_merge_makes_one_group_of_alternatives():
    prop = {"fact_id": "host", "action": "merge_with", "merge": ["loss"]}
    new = pf.apply_proposal(CASE, prop)
    assert [f["id"] for f in new["facts"]["need"]] == ["host+loss"]
    assert new["facts"]["need"][0]["fr"] == ["hote1", "100 ?%"]


def test_drop_and_unknown_fact():
    assert [f["id"] for f in pf.apply_proposal(CASE, {"fact_id": "loss", "action": "drop"})["facts"]["need"]] == ["host"]
    with pytest.raises(ValueError):
        pf.apply_proposal(CASE, {"fact_id": "nope", "action": "drop"})


def test_checks_reference_and_answers():
    prop = {"fact_id": "host", "action": "add_alternatives", "fr": ["\\bcode 1\\b"], "en": ["\\bcode 1\\b"]}
    answers = [{"lang": "fr", "out": "Échec code 1, 100 % de perte."}, {"lang": "fr", "out": "Échec."}]
    chk = pf.check(CASE, prop, answers)
    assert chk["regex_ok"] and chk["reference_passes"]
    assert chk["before"] == [0.5, 0.0] and chk["after"] == [1.0, 0.0]
    assert chk["newly_full"] == 1


def test_bad_regex_is_reported_not_raised():
    chk = pf.check(CASE, {"fact_id": "host", "action": "add_alternatives", "fr": ["("], "en": ["x"]}, [])
    assert chk["regex_ok"] is False


def test_select_cases_prefers_lost_points_and_caps_families():
    per = {"a@fr": 0.5, "a@en": 0.5, "b@fr": 1.0, "b@en": 1.0, "c@fr": 0.0, "c@en": 0.5}
    fam = {"a": "x", "b": "x", "c": "y"}
    assert pf.select_cases([per], fam, n=2, per_family=5) == ["c", "a"]
    assert pf.select_cases([per], fam, n=3, per_family=1) == ["c", "a"]
