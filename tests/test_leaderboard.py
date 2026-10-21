"""leaderboard.py: table generation, including from an alternate results directory
(a separate, clearly labeled section for a non-standard protocol, never the main table)."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmark"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


leaderboard = load("termspeak_leaderboard", BENCH / "tools" / "leaderboard.py")


def make_result(tmp_path, label, lang, split, score):
    path = tmp_path / f"{label}_{lang}_{split}.json"
    path.write_text(json.dumps({
        "lang": lang, "split": split, "model": {"label": label},
        "summary": {"score": score, "fact_recall": score, "forbidden_rate": 0.0},
        "backend": {"name": "llama.cpp", "version": "test"}, "hardware": None,
        "hardware_note": "test rig",
    }), encoding="utf-8")
    return path


def test_rows_defaults_to_the_main_results_directory():
    rows = leaderboard.rows("test")
    assert rows  # the repo's real results/*.json test-split files
    assert all("steph-protocol" not in r["file"] for r in rows)


def test_rows_reads_an_alternate_directory(tmp_path):
    make_result(tmp_path, "some-model", "fr", "test", 42.0)
    rows = leaderboard.rows("test", tmp_path)
    assert len(rows) == 1
    assert rows[0]["model"] == "some-model"
    assert rows[0]["score"] == 42.0


def test_table_links_point_into_the_given_directory(tmp_path):
    sub = tmp_path / "steph-protocol"
    sub.mkdir()
    make_result(sub, "some-model", "en", "test", 10.0)
    md = leaderboard.table("test", sub)
    assert f"steph-protocol/{sorted(sub.glob('*.json'))[0].name}" in md


def test_main_leaderboard_never_sees_an_alternate_directory_run(tmp_path):
    sub = tmp_path / "steph-protocol"
    sub.mkdir()
    make_result(sub, "some-model-steph-protocol", "fr", "test", 99.0)
    default_rows = leaderboard.rows("test")
    assert all(r["model"] != "some-model-steph-protocol" for r in default_rows)
