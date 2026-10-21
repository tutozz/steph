import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bench/matrix/finetune/compose_r1.py"


def row(source, user, answer="ok", system="sys"):
    return {"source": source, "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user},
                                           {"role": "assistant", "content": answer}]}


def write(folder, train, val):
    folder.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("val", val)):
        (folder / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def read(folder, name):
    return [json.loads(line) for line in (folder / f"{name}.jsonl").open()]


def run(tmp_path, *extra):
    out = subprocess.run([sys.executable, str(SCRIPT), "--base", str(tmp_path / "base"), "--extra", str(tmp_path / "extra"),
                          "--out", str(tmp_path / "out"), *extra], capture_output=True, text=True, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])


def test_extra_rows_are_added_and_duplicates_of_the_base_dropped(tmp_path):
    write(tmp_path / "base", [row("fr_summary", "a"), row("qa", "q1")], [row("fr_summary", "v")])
    write(tmp_path / "extra", [row("qa", "q1"), row("qa_en", "q2")], [row("qa", "q3")])
    counts = run(tmp_path)
    assert sorted(r["messages"][1]["content"] for r in read(tmp_path / "out", "train")) == ["a", "q1", "q2"]
    assert sorted(r["messages"][1]["content"] for r in read(tmp_path / "out", "val")) == ["q3", "v"]
    assert counts["extra_duplicate"] == 1


def test_repeat_only_touches_the_training_split_of_the_named_source(tmp_path):
    write(tmp_path / "base", [row("en_summary", "e1"), row("fr_summary", "f1")], [row("en_summary", "ev")])
    write(tmp_path / "extra", [], [])
    counts = run(tmp_path, "--repeat", "en_summary=3")
    train = read(tmp_path / "out", "train")
    assert sum(r["source"] == "en_summary" for r in train) == 3
    assert sum(r["source"] == "fr_summary" for r in train) == 1
    assert len(read(tmp_path / "out", "val")) == 1
    assert counts["train_by_source"] == {"en_summary": 3, "fr_summary": 1}


def test_keep_subsamples_deterministically_in_training_only(tmp_path):
    base = [row("detail", f"d{i}") for i in range(200)] + [row("fr_summary", "f")]
    write(tmp_path / "base", base, [row("detail", "dv")])
    write(tmp_path / "extra", [], [])
    run(tmp_path, "--keep", "detail=0.5")
    first = [r["messages"][1]["content"] for r in read(tmp_path / "out", "train")]
    run(tmp_path, "--keep", "detail=0.5")
    assert first == [r["messages"][1]["content"] for r in read(tmp_path / "out", "train")]
    kept = sum(c.startswith("d") for c in first)
    assert 70 <= kept <= 130
    assert "f" in first
    assert len(read(tmp_path / "out", "val")) == 1
