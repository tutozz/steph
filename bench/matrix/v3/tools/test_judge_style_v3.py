"""Tests of the spoken-style pairwise judge (judge_style_v3.py), X5.

    python3 -m pytest bench/matrix/v3/tools/test_judge_style_v3.py -q

SPDX-License-Identifier: MIT
"""

import json

import pytest

import judge_style_v3 as js

CTX = "Commande : pytest\nStatut : échec (code 1)\nSortie :\n2 failed, 7 passed"
ALL_A = "A A A A A"
ALL_B = "B B B B B"
ALL_TIE = "= = = = ="


def test_context_comes_before_both_answers_in_the_given_order():
    msgs = js.build_messages(CTX, "first answer", "second answer", "fr")
    user = msgs[-1]["content"]
    assert msgs[0]["role"] == "system"
    assert user.index(CTX) < user.index("first answer") < user.index("second answer")
    assert "A: first answer" in user and "B: second answer" in user


def test_parse_reads_the_five_criteria_in_order():
    v = js.parse_verdict("A B = A B")
    assert v == {"clarte": "A", "ordre": "B", "concision": "=", "naturel": "A", "global": "B"}


def test_parse_rejects_an_incomplete_answer():
    assert js.parse_verdict("A B") is None
    assert js.parse_verdict("A B = A C") is None


def test_stable_verdict_is_kept_across_both_orders():
    # x shown first says A, x shown second says B: x wins both times
    calls = iter([ALL_A, ALL_B])
    res = js.judge_pair(lambda m: next(calls), CTX, "x answer", "y answer", "fr")
    assert res["final"]["global"] == "x"
    assert all(res["final"][k] == "x" for k in js.CRITERIA)


def test_position_following_verdict_becomes_a_tie():
    # the judge always prefers whatever is shown first: unstable, so a tie
    calls = iter([ALL_A, ALL_A])
    res = js.judge_pair(lambda m: next(calls), CTX, "x answer", "y answer", "fr")
    assert res["final"]["global"] == "="
    assert res["unstable"]["global"] is True


def test_second_order_really_swaps_the_answers():
    seen = []

    def call(messages):
        seen.append(messages[-1]["content"])
        return ALL_TIE

    js.judge_pair(call, CTX, "x answer", "y answer", "en")
    assert seen[0].index("x answer") < seen[0].index("y answer")
    assert seen[1].index("y answer") < seen[1].index("x answer")


def test_identical_answers_are_a_tie_without_calling_the_judge():
    def call(messages):
        raise AssertionError("judge called on identical answers")

    res = js.judge_pair(call, CTX, "Deux tests en échec.", " Deux tests en échec. ", "fr", skip_identical=True)
    assert res["identical"] is True and res["final"]["global"] == "="


def test_unparsable_judge_answer_is_retried_then_a_tie():
    calls = iter(["nonsense"] * 10)
    res = js.judge_pair(lambda m: next(calls), CTX, "x", "y", "fr")
    assert res["final"]["global"] == "=" and res["error"] is True


def test_position_bias_counts_first_position_wins_among_decided_raw_verdicts():
    results = [
        {"raw": [{"global": "A"}, {"global": "A"}]},
        {"raw": [{"global": "A"}, {"global": "B"}]},
        {"raw": [{"global": "="}, {"global": "="}]},
    ]
    bias = js.position_bias(results, "global")
    assert bias == {"decided": 4, "first_wins": 3, "first_share": 75.0}


def test_control_agreement_expects_good_to_win_and_identical_to_tie():
    results = [
        {"expected": "x", "final": {"global": "x"}},
        {"expected": "x", "final": {"global": "="}},
        {"expected": "=", "final": {"global": "="}},
        {"expected": "=", "final": {"global": "y"}},
    ]
    agg = js.control_agreement(results, "global")
    assert agg["planted"] == {"n": 2, "agree": 1, "rate": 50.0}
    assert agg["identical"] == {"n": 2, "agree": 1, "rate": 50.0}
    assert agg["all"]["rate"] == 50.0


def test_tally_counts_wins_losses_and_ties_per_criterion():
    results = [{"final": {k: "x" for k in js.CRITERIA}}, {"final": {k: "y" for k in js.CRITERIA}},
               {"final": {k: "=" for k in js.CRITERIA}}, {"final": {k: "x" for k in js.CRITERIA}}]
    t = js.tally(results)
    assert t["global"] == {"x": 2, "y": 1, "=": 1, "n": 4, "net_x": 25.0}


def test_pairs_from_runs_match_rows_by_id_and_skip_missing(tmp_path):
    harness = [{"id": "c1@fr", "kind": "summary", "messages": [{"role": "system", "content": "s"},
                                                              {"role": "user", "content": CTX}]},
               {"id": "c2@en", "kind": "summary", "messages": [{"role": "user", "content": "u2"}]}]
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({"rows": [{"id": "c1@fr", "out": "<think>x</think>Deux échecs."}, {"id": "c2@en", "out": None}]}))
    b.write_text(json.dumps({"rows": [{"id": "c1@fr", "out": "Two fails."}, {"id": "c2@en", "out": "y"}]}))
    pairs = js.pairs_from_runs(harness, a, b)
    assert pairs == [{"id": "c1@fr", "lang": "fr", "context": CTX, "x": "Deux échecs.", "y": "Two fails."}]


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_prompt_names_the_answer_language(lang):
    user = js.build_messages(CTX, "a", "b", lang)[-1]["content"]
    assert ("French" if lang == "fr" else "English") in user
