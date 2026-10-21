"""Tests of the generic-profile rewrite: python3 -m pytest bench/matrix/finetune/gemma/test_gemma_format.py

SPDX-License-Identifier: MIT
"""

from gemma_format import label, lf, prompts, to_generic

USER = {"role": "user", "content": "Commande : ls\nStatut : succès\nDurée : 0.1 s ; 2 lignes affichées\nSortie :\na\nb"}
ANSWER = {"role": "assistant", "content": "2 éléments : a, b."}


def test_summary_fr_gets_production_prompt():
    out, known = to_generic([{"role": "system", "content": label.TRAIN_SYSTEM}, USER, ANSWER])
    assert known
    assert out[0]["content"] == prompts.SUMMARY_SYSTEM
    assert out[1:] == [USER, ANSWER]


def test_each_feature_prompt_maps_to_its_production_prompt():
    pairs = [(label.TRAIN_SYSTEM_EN, prompts.SUMMARY_SYSTEM_EN), (lf.TRAIN_DETAILS_SYSTEM, prompts.DETAILS_SYSTEM),
             (lf.TRAIN_DETAILS_SYSTEM_EN, prompts.DETAILS_SYSTEM_EN), (lf.TRAIN_START_SYSTEM, prompts.START_SYSTEM),
             (lf.TRAIN_PROGRESS_SYSTEM_EN, prompts.PROGRESS_SYSTEM_EN)]
    for train, generic in pairs:
        out, known = to_generic([{"role": "system", "content": train}, USER, ANSWER])
        assert known and out[0]["content"] == generic


def test_question_rows_are_already_generic():
    msgs = [{"role": "system", "content": prompts.QA_SYSTEM}, USER, ANSWER]
    out, known = to_generic(msgs)
    assert known and out == msgs


def test_unknown_system_prompt_is_flagged_and_untouched():
    msgs = [{"role": "system", "content": "autre prompt"}, USER, ANSWER]
    out, known = to_generic(msgs)
    assert not known and out == msgs


def test_input_is_not_mutated():
    msgs = [{"role": "system", "content": label.TRAIN_SYSTEM}, USER, ANSWER]
    to_generic(msgs)
    assert msgs[0]["content"] == label.TRAIN_SYSTEM
