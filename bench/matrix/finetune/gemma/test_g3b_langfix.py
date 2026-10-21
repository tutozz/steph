"""Tests of the G3b language fix: PYTHONPATH=src python3 -m pytest bench/matrix/finetune/gemma/test_g3b_langfix.py

SPDX-License-Identifier: MIT
"""

import hashlib

from g3b_langfix import EN_NOTE, en_rows, is_french_output, keep_ok, labeled_row, select, teacher_messages

FR_OUT = "Suppression de fichier.txt : aucun fichier ou dossier de ce type\nerreur : le fichier est introuvable"
EN_OUT = "rm: cannot remove 'file.txt': No such file or directory\nerror: the file is not found"


def rec(output, cmd="rm file.txt", exit_=1):
    return {"cmd": cmd, "exit": exit_, "duration": 0.1, "output": output, "machine": "m", "category": "files"}


def labeled(label, user="Command: rm\nOutput:\nx"):
    return {"label": label, "train_messages": [{"role": "system", "content": "s"},
                                               {"role": "user", "content": user},
                                               {"role": "assistant", "content": label}]}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def test_french_output_is_detected():
    assert is_french_output(FR_OUT)


def test_english_output_is_not_french():
    assert not is_french_output(EN_OUT)


def test_output_with_too_few_french_words_is_not_kept():
    assert not is_french_output("le 42")


def test_select_keeps_french_outputs_once_and_caps_n():
    recs = [rec(FR_OUT), rec(FR_OUT), rec(EN_OUT)] + [rec(FR_OUT, cmd=f"rm f{i}") for i in range(5)]
    got, counts = select(recs, n=3, seed=0)
    assert len(got) == 3
    assert len({(r["cmd"], r["output"]) for r in got}) == 3
    assert counts == {"records": 8, "french": 7, "unique": 6, "selected": 3}


def test_select_is_deterministic_for_a_seed():
    recs = [rec(FR_OUT, cmd=f"rm f{i}") for i in range(20)]
    assert select(recs, n=5, seed=1)[0] == select(recs, n=5, seed=1)[0]


def test_en_rows_keep_english_labels_only():
    rows, counts = en_rows([labeled("Failed: file.txt not found, no such file."),
                            labeled("Échec : fichier introuvable, aucun fichier de ce type."),
                            labeled("42")])
    assert [r["messages"][2]["content"] for r in rows] == ["Failed: file.txt not found, no such file."]
    assert rows[0]["source"] == "langfix_en_fr"
    assert counts == {"labeled": 3, "en": 1, "fr": 1, "undetermined": 1}


def test_keep_ok_drops_invention_doubtful_and_unjudged():
    rows = [{"source": "langfix_en_fr", "messages": labeled("a", user=u)["train_messages"]} for u in ("u1", "u2", "u3", "u4")]
    verdicts = [{"sha": sha("u1"), "verdict": "ok"}, {"sha": sha("u2"), "verdict": "invention"},
                {"sha": sha("u3"), "verdict": "douteux"}]
    got, counts = keep_ok(rows, verdicts, n=10, seed=0)
    assert [r["messages"][1]["content"] for r in got] == ["u1"]
    assert counts == {"candidates": 4, "ok": 1, "invention": 1, "douteux": 1, "unjudged": 1, "kept": 1}


def test_keep_ok_caps_n():
    rows = [{"source": "langfix_en_fr", "messages": labeled("a", user=f"u{i}")["train_messages"]} for i in range(10)]
    verdicts = [{"sha": sha(f"u{i}"), "verdict": "ok"} for i in range(10)]
    got, counts = keep_ok(rows, verdicts, n=4, seed=0)
    assert len(got) == 4 and counts["kept"] == 4


def test_teacher_gets_the_language_note_the_student_never_sees():
    msgs = [{"role": "system", "content": "Say it in English."}, {"role": "user", "content": "Command: rm\nOutput:\nerreur"}]
    teacher = teacher_messages(msgs)
    assert teacher[0]["content"] == "Say it in English. " + EN_NOTE
    assert teacher[1] == msgs[1] and msgs[0]["content"] == "Say it in English."
    row = labeled_row(rec(FR_OUT), msgs, "Failed: file not found.")
    assert [m["role"] for m in row["train_messages"]] == ["system", "user", "assistant"]
    assert EN_NOTE not in row["train_messages"][0]["content"]
    assert row["train_messages"][1]["content"] == msgs[1]["content"]
    assert row["train_messages"][2]["content"] == row["label"] == "Failed: file not found."
