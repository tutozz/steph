"""Tests des parties pures de x4_relabel.py (X4) : construction des tâches depuis final/, assemblage
des nouvelles étiquettes, comptes sans texte. Aucun réseau, aucun LLM."""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import x4_relabel  # noqa: E402
from label_features import TEACHER_DETAILS_SYSTEM, TRAIN_DETAILS_SYSTEM  # noqa: E402

from steph.prompts import PROGRESS_SYSTEM, SUMMARY_SYSTEM, SUMMARY_SYSTEM_EN  # noqa: E402


def sha(t):
    return hashlib.sha256(t.encode()).hexdigest()


def row(user, label, system="train"):
    return {"source": "s", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user},
                                        {"role": "assistant", "content": label}]}


def write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def make_final(tmp_path):
    final = tmp_path / "final"
    final.mkdir()
    write(final / "macos.jsonl", [row("sortie A", "ancien A"), row("sortie B", "ancien B")])
    write(final / "linux-dev.jsonl", [row("sortie A", "ancien A bis")])
    for f in ("linux-low", "snapshot-linux-dev", "snapshot-linux-low", "linux-low.en", "flux"):
        write(final / f"{f}.jsonl", [])
    write(final / "macos.en.jsonl", [row("output C", "old C")])
    write(final / "progress.jsonl", [row("en cours D", "ancien D")])
    write(final / "detail.jsonl", [row("détail E", "ancien E"), row("détail F", "ancien F"), row("hors K3", "x")])
    hashes = tmp_path / "hashes"
    hashes.mkdir()
    (hashes / "detail-k3-all.txt").write_text(sha("détail E") + "\n" + sha("détail F") + "\n")
    (hashes / "detail-k3.txt").write_text(sha("détail F") + "\n")
    return final, hashes


def test_build_one_task_per_distinct_input(tmp_path):
    final, hashes = make_final(tmp_path)
    tasks = x4_relabel.build_tasks(final, hashes)
    by = {}
    for t in tasks:
        by.setdefault(t["task"], []).append(t)
    assert len(by["fr_summary"]) == 2  # « sortie A » dans deux fichiers : étiquetée une fois
    assert len(by["en_summary"]) == 1 and len(by["progress"]) == 1
    assert len(by["detail"]) == 2  # seulement les entrées du détail K3
    assert {t["sha"]: t["k3_rejected"] for t in by["detail"]} == {sha("détail E"): False, sha("détail F"): True}


def test_teacher_prompts_are_the_production_ones(tmp_path):
    final, hashes = make_final(tmp_path)
    systems = {t["task"]: t["teacher_messages"][0]["content"] for t in x4_relabel.build_tasks(final, hashes)}
    assert systems == {"fr_summary": SUMMARY_SYSTEM, "en_summary": SUMMARY_SYSTEM_EN, "progress": PROGRESS_SYSTEM,
                       "detail": TEACHER_DETAILS_SYSTEM}


def test_clean_uses_the_points_join_for_detail_only():
    assert x4_relabel.clean_for("detail", "Erreur E404\n3 absents") == ("Erreur E404. 3 absents", "ok")
    assert x4_relabel.clean_for("progress", "Compile\nle module") == ("Compile le module", "ok")
    assert x4_relabel.clean_for("fr_summary", "Succès\n3 fichiers") == ("Succès 3 fichiers", "ok")


def test_assemble_replaces_labels_and_counts(tmp_path):
    final, hashes = make_final(tmp_path)
    tasks = x4_relabel.build_tasks(final, hashes)
    tid = {(t["task"], t["sha"]): t["tid"] for t in tasks}
    labels = {tid[("fr_summary", sha("sortie A"))]: "nouveau A",
              tid[("fr_summary", sha("sortie B"))]: "ancien B",
              tid[("en_summary", sha("output C"))]: None,  # rejeté par clean : la ligne sort du corpus
              tid[("progress", sha("en cours D"))]: "nouveau D",
              tid[("detail", sha("détail E"))]: "E. point",
              tid[("detail", sha("détail F"))]: "F. point"}
    verdicts = {tid[("detail", sha("détail F"))]: "invention"}
    out = tmp_path / "out"
    counts = x4_relabel.assemble(final, tasks, labels, verdicts, out)
    mac = [json.loads(l) for l in open(out / "macos.jsonl")]
    assert [r["messages"][-1]["content"] for r in mac] == ["nouveau A", "ancien B"]
    assert [json.loads(l)["messages"][-1]["content"] for l in open(out / "linux-dev.jsonl")] == ["nouveau A"]
    assert (out / "macos.en.jsonl").read_text() == ""
    detail = [json.loads(l) for l in open(out / "detail.jsonl")]
    assert [r["messages"][-1]["content"] for r in detail] == ["E. point"]  # F rejeté au juge, hors K3 absent
    assert detail[0]["messages"][0]["content"] == TRAIN_DETAILS_SYSTEM  # prompt resserré de K3, pas celui de H3a
    assert mac[0]["messages"][0]["content"] == "train"
    assert counts["fr_summary"] == {"rows": 3, "changed": 2, "identical": 1, "dropped": 0}
    assert counts["en_summary"] == {"rows": 1, "changed": 0, "identical": 0, "dropped": 1}
    assert counts["detail"] == {"rows": 2, "changed": 1, "identical": 0, "dropped": 1}
    assert not (out / "start.jsonl").exists()


def test_assemble_is_text_free_in_counts(tmp_path):
    final, hashes = make_final(tmp_path)
    tasks = x4_relabel.build_tasks(final, hashes)
    counts = x4_relabel.assemble(final, tasks, {t["tid"]: "nouveau" for t in tasks}, {}, tmp_path / "o")
    assert "nouveau" not in json.dumps(counts) and "sortie" not in json.dumps(counts)
