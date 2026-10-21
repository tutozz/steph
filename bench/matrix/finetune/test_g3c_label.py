"""Tests of the G3c public labeling: PYTHONPATH=src python3 -m pytest bench/matrix/finetune/test_g3c_label.py

SPDX-License-Identifier: MIT
"""

import hashlib

import label
from g3c_label import build_tasks, candidate_row, final_verdict, is_val, teacher_messages


def rec(output="1404 passed, 7 skipped in 14.62s", cmd="python3 -m pytest -q tests", lang="fr", exit_=0):
    return {"cmd": cmd, "exit": exit_, "duration": 15.2, "output": output, "lang": lang, "family": "tests",
            "source": "attrs (MIT)", "fault": "", "scenario": 0, "source_license": "attrs (MIT)"}


def test_task_holds_the_exact_production_messages():
    r = rec()
    task = build_tasks([r])[0]
    assert task["teacher_messages"] == label.build_messages(r, 587, "fr")
    assert task["id"] == "fr:g3c:0"


def test_english_record_gets_english_production_prompt():
    task = build_tasks([rec(lang="en")])[0]
    assert task["teacher_messages"] == label.build_messages(rec(lang="en"), 587, "en")
    assert task["teacher_messages"][1]["content"].startswith("Command: ")


def test_duplicate_user_messages_are_labeled_once():
    tasks = build_tasks([rec(), rec(), rec(lang="en")])
    assert [t["id"] for t in tasks] == ["fr:g3c:0", "en:g3c:2"]


def test_teacher_note_is_appended_to_the_teacher_system_only():
    msgs = label.build_messages(rec(), 587, "fr")
    got = teacher_messages(msgs, "fr", note=True)
    assert got[0]["content"].startswith(msgs[0]["content"]) and got[0]["content"] != msgs[0]["content"]
    assert got[1:] == msgs[1:]
    assert teacher_messages(msgs, "fr", note=False) == msgs


def test_candidate_row_uses_training_system_and_production_user():
    task = build_tasks([rec()])[0]
    row, why = candidate_row(task, "Succès : 1404 tests passés, 7 ignorés.")
    assert why == "ok"
    assert row["messages"] == [
        {"role": "system", "content": label.TRAIN_SYSTEM},
        {"role": "user", "content": task["teacher_messages"][1]["content"]},
        {"role": "assistant", "content": "Succès : 1404 tests passés, 7 ignorés."},
    ]
    assert row["id"] == "fr:g3c:0" and row["lang"] == "fr" and row["family"] == "tests"


def test_candidate_row_drops_a_label_in_the_other_language():
    task = build_tasks([rec()])[0]
    row, why = candidate_row(task, "All the tests passed, and 7 of them were skipped.")
    assert row is None and why == "langue"


def test_candidate_row_keeps_a_french_label_full_of_copied_english_words():
    out = "test -f config.h || make stamp-h1\nmake all-recursive\nmake: *** [Makefile:561: all] Error 141"
    task = build_tasks([rec(output=out, cmd="make -n | head")])[0]
    row, why = candidate_row(task, "3 éléments : test -f config.h, make stamp-h1, make all-recursive.")
    assert why == "ok" and row is not None


def test_candidate_row_drops_a_missing_label():
    assert candidate_row(build_tasks([rec()])[0], None) == (None, "vide")


def test_final_verdict_keeps_9b_ok_and_27b_cleared_only():
    assert final_verdict("ok", None) == "ok"
    assert final_verdict("douteux", "ok") == "ok"
    assert final_verdict("invention", "ok") == "ok"
    assert final_verdict("invention", "douteux") == "rejet"
    assert final_verdict("douteux", "invention") == "rejet"
    assert final_verdict("douteux", None) == "rejet"
    assert final_verdict("erreur", None) == "rejet"


def test_val_split_is_stable_and_about_five_percent():
    users = [f"Commande : c{i}" for i in range(2000)]
    val = [u for u in users if is_val(u)]
    assert 60 <= len(val) <= 140
    assert is_val(users[0]) == (int(hashlib.sha256(users[0].encode()).hexdigest(), 16) % 20 == 0)
