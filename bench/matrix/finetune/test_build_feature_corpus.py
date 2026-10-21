"""Tests des parties pures de build_feature_corpus.py (H3a) : fenêtrage de la
progression et du flux, filtrage par resolve(). Aucun réseau, aucun LLM."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audit_pii import load_names  # noqa: E402
from build_feature_corpus import flux_deltas, progress_windows, scan_and_drop, summary_residual  # noqa: E402


def test_progress_windows_empty_below_minimum_lines():
    assert progress_windows("a\nb\nc\n", 30.0) == []


def test_progress_windows_returns_three_growing_snapshots():
    lines = [f"line {i}" for i in range(20)]
    windows = progress_windows("\n".join(lines), 100.0)
    assert len(windows) == 3
    elapsed = [e for e, _ in windows]
    assert elapsed == sorted(elapsed)
    assert elapsed[0] < elapsed[-1] < 100.0
    # chaque fenêtre ne montre que ce qui est déjà "affiché" à cet instant
    _, last_recent = windows[-1]
    assert "line 19" not in last_recent or "line 17" in last_recent


def test_progress_windows_never_exceeds_tail_lines():
    lines = [f"line {i}" for i in range(60)]
    windows = progress_windows("\n".join(lines), 200.0, tail=15)
    for _, recent in windows:
        assert len(recent.splitlines()) <= 15


def test_flux_deltas_splits_into_at_most_n_windows():
    lines = [f"log {i}" for i in range(40)]
    deltas = flux_deltas("\n".join(lines), n_windows=4)
    assert len(deltas) <= 4
    assert sum(len(d) for d in deltas) == 40


def test_flux_deltas_empty_output():
    assert flux_deltas("") == []


def test_flux_deltas_keeps_order():
    lines = [f"log {i}" for i in range(10)]
    deltas = flux_deltas("\n".join(lines), n_windows=3)
    flat = [l for d in deltas for l in d]
    assert flat == lines


def test_summary_residual_drops_records_resolve_already_handles():
    resolved = {"cmd": "gcc -Wall -c a.c", "exit": 1,
                "output": "a.c:1:1: error: expected expression\na.c:2:1: error: expected ';'\n2 errors generated"}
    unresolved = {"cmd": "some-unknown-linter run", "exit": 1, "output": "totally unrecognized failure format\n"}
    kept, stats = summary_residual([resolved, unresolved])
    assert kept == [unresolved]
    assert stats == {"total": 2, "resolved_in_code": 1, "residual": 1}


def test_scan_and_drop_removes_rows_matching_the_private_name_list(tmp_path):
    names_file = tmp_path / "names.tsv"
    names_file.write_text("zzz-test-secret-name\tredacted\n", encoding="utf-8")
    names = load_names(str(names_file))
    clean_row = {"messages": [{"role": "user", "content": "Commande : ls\nSortie :\nfoo.txt"}]}
    leaking_row = {"messages": [{"role": "user", "content": "Commande : ls\nSortie :\nzzz-test-secret-name"}]}
    kept, dropped = scan_and_drop([clean_row, leaking_row], names)
    assert kept == [clean_row]
    assert dropped == 1


# ---------------------------------------------------------------- R1 : entrées anglaises

def _rec(cmd="make", exit_code=2, output="error: x\n"):
    return {"cmd": cmd, "exit": exit_code, "duration": 3.0, "output": output, "id": "r1", "machine": "m"}


def test_english_detail_entry_is_what_steph_sends_in_english():
    from build_feature_corpus import MAX_CHARS, detail_entry
    from steph.digest import digest
    from steph.prompts import details_messages
    from steph.textproc import compact_output
    rec = _rec()
    out = digest(rec["cmd"], rec["output"], MAX_CHARS, "en") or compact_output(rec["output"].splitlines(), MAX_CHARS)
    row = detail_entry(rec, "en")
    assert row["messages"] == details_messages("make", 2, 3.0, out, 1, language="en")
    assert row["source"] == "detail.en" and row["mode"] == "detail"


def test_english_start_and_progress_entries_use_the_english_prompts():
    from build_feature_corpus import progress_entries, start_entry
    from steph.prompts import PROGRESS_SYSTEM_EN, START_SYSTEM_EN
    assert start_entry(_rec(), "en")["messages"][0]["content"] == START_SYSTEM_EN
    assert start_entry(_rec(), "en")["source"] == "start.en"
    long_rec = _rec(output="".join(f"compiling unit {i}\n" for i in range(40)))
    rows = progress_entries(long_rec, "en")
    assert rows and all(r["messages"][0]["content"] == PROGRESS_SYSTEM_EN for r in rows)
    assert {r["source"] for r in rows} == {"progress.en"} and {r["mode"] for r in rows} == {"progress"}


def test_french_entries_are_unchanged_by_default():
    from build_feature_corpus import detail_entry, start_entry
    from steph.prompts import DETAILS_SYSTEM, START_SYSTEM
    assert detail_entry(_rec())["messages"][0]["content"] == DETAILS_SYSTEM
    assert detail_entry(_rec())["source"] == "detail"
    assert start_entry(_rec())["messages"][0]["content"] == START_SYSTEM


def test_cli_english_writes_only_english_feature_files(tmp_path):
    import json
    import subprocess
    import sys as _sys
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    rec = {"cmd": "make", "exit": 2, "duration": 30.0, "category": "compilation",
           "output": "".join(f"compiling unit {i}\n" for i in range(40)), "machine": "m"}
    (corpus / "macos.en.jsonl").write_text(json.dumps(rec) + "\n")
    names = tmp_path / "names.tsv"
    names.write_text("")
    script = Path(__file__).parent / "build_feature_corpus.py"
    subprocess.run([_sys.executable, str(script), "--corpus-dir", str(corpus), "--out-dir", str(tmp_path / "out"),
                    "--lang", "en", "--names", str(names)], check=True, capture_output=True)
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["detail.en.jsonl", "progress.en.jsonl", "start.en.jsonl"]
