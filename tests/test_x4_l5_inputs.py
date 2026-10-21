"""L5 : x4_l5_inputs.py réécrit les entrées de data/final-x4 avec le bloc de faits, sans toucher aux
étiquettes. Corpus synthétique écrit pour le test, jamais recopié du corpus réel."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench/matrix/finetune"))
sys.path.insert(0, str(ROOT / "tests"))

import x4_l5_inputs  # noqa: E402
from label import build_messages, strip_facts_block  # noqa: E402
from test_l5_corpus_alignment import RECORDS, without_facts  # noqa: E402

DETAIL = {"source": "detail", "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                                           {"role": "assistant", "content": "a"}]}


def labeled(rec, lang, label):
    return {"source": "macos", "id": rec["id"], "messages": [
        {"role": "system", "content": "prompt d'enseignant"}, without_facts(rec, 1500, lang),
        {"role": "assistant", "content": label}]}


def write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def corpus(tmp_path):
    final, raw = tmp_path / "final-x4", tmp_path / "corpus"
    final.mkdir()
    raw.mkdir()
    write(raw / "macos.jsonl", RECORDS)
    write(raw / "macos.en.jsonl", RECORDS)
    orphan = {**RECORDS[0], "cmd": "./absent.sh"}
    write(final / "macos.jsonl", [labeled(r, "fr", f"étiquette {i}") for i, r in enumerate(RECORDS)]
          + [labeled(orphan, "fr", "sans brut")])
    write(final / "macos.en.jsonl", [labeled(r, "en", f"label {i}") for i, r in enumerate(RECORDS)])
    write(final / "detail.jsonl", [DETAIL])
    (final / "README.txt").write_text("corpus X4\n")
    return final, raw


def read(path):
    return [json.loads(l) for l in path.open(encoding="utf-8")]


def run(tmp_path):
    final, raw = corpus(tmp_path)
    out = tmp_path / "final-x4-l5"
    report = x4_l5_inputs.main(["--final", str(final), "--raw", *map(str, sorted(raw.glob("*.jsonl"))),
                                "--out", str(out)])
    return final, out, report


def test_summary_inputs_gain_the_production_facts_block_and_labels_stay(tmp_path):
    final, out, _ = run(tmp_path)
    for name, lang in (("macos.jsonl", "fr"), ("macos.en.jsonl", "en")):
        old, new = read(final / name), read(out / name)
        assert len(new) == len(old)
        for i, rec in enumerate(RECORDS):
            assert new[i]["messages"][1] == build_messages(rec, 1500, lang)[1]
            assert new[i]["messages"][0] == old[i]["messages"][0]
            assert new[i]["messages"][2] == old[i]["messages"][2]
            assert {k: v for k, v in new[i].items() if k != "messages"} == \
                   {k: v for k, v in old[i].items() if k != "messages"}
            assert strip_facts_block(new[i]["messages"][1]["content"], lang) == old[i]["messages"][1]["content"]


def test_unmatched_rows_and_other_files_are_copied_unchanged(tmp_path):
    final, out, report = run(tmp_path)
    assert read(out / "macos.jsonl")[-1] == read(final / "macos.jsonl")[-1]
    assert (out / "detail.jsonl").read_bytes() == (final / "detail.jsonl").read_bytes()
    assert report["files"]["macos.jsonl"] == {"rows": 4, "with_facts": 3, "no_facts": 0, "unmatched": 1}
    assert report["files"]["macos.en.jsonl"]["with_facts"] == 3
    assert report["files"]["detail.jsonl"] == {"rows": 1, "copied": 1}


def test_checksums_cover_every_written_file(tmp_path):
    _, out, _ = run(tmp_path)
    sums = dict(reversed(l.split("  ")) for l in (out / "SHA256SUMS").read_text().splitlines())
    assert set(sums) == {"macos.jsonl", "macos.en.jsonl", "detail.jsonl"}
    for name, digest in sums.items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    assert "L5" in (out / "README.txt").read_text()


def test_a_second_run_on_its_own_output_changes_nothing(tmp_path):
    _, out, _ = run(tmp_path)
    again = tmp_path / "again"
    raw = sorted((tmp_path / "corpus").glob("*.jsonl"))
    x4_l5_inputs.main(["--final", str(out), "--raw", *map(str, raw), "--out", str(again)])
    for name in ("macos.jsonl", "macos.en.jsonl"):
        assert (again / name).read_bytes() == (out / name).read_bytes()
