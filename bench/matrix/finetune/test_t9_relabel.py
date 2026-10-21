"""Tests des parties pures de t9_relabel.py : tâches, priorité, assemblage. Aucun réseau."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import t9_relabel as t9  # noqa: E402
from label_features import TEACHER_DETAILS_SYSTEM  # noqa: E402

from steph.prompts import PROGRESS_SYSTEM, SUMMARY_SYSTEM, SUMMARY_SYSTEM_EN  # noqa: E402


def row(user, label, system="train", **extra):
    return {"source": "s", **extra, "messages": [{"role": "system", "content": system},
                                                 {"role": "user", "content": user},
                                                 {"role": "assistant", "content": label}]}


def qa_row(ctx, question, label, category):
    return {"source": "qa-synth", "_category": category, "_key": "k", "messages": [
        {"role": "system", "content": "QA"}, {"role": "user", "content": ctx},
        {"role": "assistant", "content": "ok"}, {"role": "user", "content": question},
        {"role": "assistant", "content": label}]}


def write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def make(tmp_path):
    final = tmp_path / "final"
    final.mkdir()
    write(final / "macos.jsonl", [row("u-fr-1", "old1"), row("u-fr-2", "old2")])
    write(final / "linux-dev.jsonl", [row("u-fr-1", "old1-dup")])
    write(final / "macos.en.jsonl", [row("u-en-1", "oldEN")])
    write(final / "progress.jsonl", [row("u-p", "oldP")])
    write(final / "detail.jsonl", [row("u-d", "oldD", system="TRAIN_DETAILS")])
    (final / "README.txt").write_text("X4\n")
    qa = tmp_path / "qa_train.jsonl"
    write(qa, [qa_row("ctx", "q1", "Oui, 3.", "present"), qa_row("ctx", "q2", "Pas dans l'historique.", "absent")])
    return final, qa


def test_tasks_use_teacher_prompts_and_dedupe(tmp_path):
    final, qa = make(tmp_path)
    tasks = t9.build_tasks(final, qa)
    by = {}
    for t in tasks:
        by.setdefault(t["task"], []).append(t)
    assert len(by["fr_summary"]) == 2  # u-fr-1 présent deux fois, une seule requête
    assert by["fr_summary"][0]["teacher_messages"][0]["content"] == SUMMARY_SYSTEM
    assert by["en_summary"][0]["teacher_messages"][0]["content"] == SUMMARY_SYSTEM_EN
    assert by["progress"][0]["teacher_messages"][0]["content"] == PROGRESS_SYSTEM
    assert by["detail"][0]["teacher_messages"][0]["content"] == TEACHER_DETAILS_SYSTEM
    assert len(by["qa"]) == 1  # la question « absent » garde sa réponse canonique, sans requête
    assert by["qa"][0]["teacher_messages"][-1]["content"] == "q1"
    assert by["qa"][0]["teacher_messages"][0]["content"] == "QA"


def test_priority_order_fr_en_qa_features(tmp_path):
    final, qa = make(tmp_path)
    order = [t["task"] for t in t9.prioritized(t9.build_tasks(final, qa))]
    assert order == ["fr_summary", "fr_summary", "en_summary", "qa", "progress", "detail"]


def test_assemble_replaces_accepted_and_keeps_old_otherwise(tmp_path):
    final, qa = make(tmp_path)
    tasks = t9.build_tasks(final, qa)
    tid = {(t["task"], t["teacher_messages"][-1]["content"]): t["tid"] for t in tasks}
    labels = {
        tid[("fr_summary", "u-fr-1")]: {"label": "new1", "reason": "ok"},
        tid[("fr_summary", "u-fr-2")]: {"label": None, "reason": "trop long"},
        tid[("qa", "q1")]: {"label": "Pas dans l'historique.", "reason": "ok"},  # refus injustifié
        tid[("detail", "u-d")]: {"label": "Point un. Point deux", "reason": "ok"},
    }
    out = tmp_path / "out"
    counts = t9.assemble(final, qa, tasks, labels, out)
    mac = [json.loads(l) for l in (out / "macos.jsonl").read_text().splitlines()]
    assert [r["messages"][-1]["content"] for r in mac] == ["new1", "old2"]
    dev = [json.loads(l) for l in (out / "linux-dev.jsonl").read_text().splitlines()]
    assert dev[0]["messages"][-1]["content"] == "new1"
    assert dev[0]["label_source"] == "t9"
    assert mac[1]["label_source"] == "x4"
    q = [json.loads(l) for l in (out / "qa_train.jsonl").read_text().splitlines()]
    assert [r["messages"][-1]["content"] for r in q] == ["Oui, 3.", "Pas dans l'historique."]
    det = json.loads((out / "detail.jsonl").read_text())
    assert det["messages"][0]["content"] == "TRAIN_DETAILS"
    assert det["messages"][-1]["content"] == "Point un. Point deux"
    assert counts["fr_summary"] == {"rows": 3, "t9": 2, "kept_x4": 1, "rejected": 1, "unlabeled": 0}
    assert counts["qa"]["kept_x4"] == 2
    assert (out / "SHA256SUMS").read_text().count(".jsonl") == 6
    assert "T9" in (out / "README.txt").read_text()


def test_assemble_keeps_rows_without_label_when_budget_stopped(tmp_path):
    final, qa = make(tmp_path)
    tasks = t9.build_tasks(final, qa)
    counts = t9.assemble(final, qa, tasks, {}, tmp_path / "out")
    assert counts["progress"] == {"rows": 1, "t9": 0, "kept_x4": 1, "rejected": 0, "unlabeled": 1}
    rows = [json.loads(l) for l in (tmp_path / "out" / "progress.jsonl").read_text().splitlines()]
    assert rows[0]["messages"][-1]["content"] == "oldP"
