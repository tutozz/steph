"""X4 : leak_check lit aussi les enregistrements bruts (cmd, output) des sorties de bac à sable,
pas seulement les exemples à `messages`."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from leak_check import examples_from_jsonl, scan_texts  # noqa: E402


def test_raw_record_gives_command_and_output(tmp_path):
    p = tmp_path / "raw.jsonl"
    p.write_text(json.dumps({"cmd": "pytest -q", "exit": 1, "output": "1 failed, 3 passed"}) + "\n")
    [(text, canary)] = list(examples_from_jsonl(p))
    assert "pytest -q" in text and "1 failed, 3 passed" in text and canary is False


def test_raw_record_is_matched_on_its_command(tmp_path):
    p = tmp_path / "raw.jsonl"
    p.write_text(json.dumps({"cmd": "pytest -q", "exit": 1, "output": "a b c d e\nf g h i j"}) + "\n")
    from leak_check import fp, norm_cmd
    lines, sh = fp("a b c d e\nf g h i j")
    cp = {"id": "c", "cmds": [norm_cmd("pytest -q")], "reps": [{"lines": sorted(lines), "shingles": sorted(sh)}]}
    res = scan_texts([cp], examples_from_jsonl(p))
    assert res["cases"][0]["rejected"] and res["cases"][0]["same_cmd_line"] == 1.0


def test_messages_example_unchanged(tmp_path):
    p = tmp_path / "ex.jsonl"
    p.write_text(json.dumps({"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                                          {"role": "assistant", "content": "a"}]}) + "\n")
    assert list(examples_from_jsonl(p)) == [("u", False)]


def test_preference_pair_prompt_is_read(tmp_path):
    p = tmp_path / "pairs.jsonl"
    p.write_text(json.dumps({"prompt": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
                             "chosen": "c", "rejected": "r"}) + "\n")
    assert list(examples_from_jsonl(p)) == [("u", False)]


def test_drop_removes_only_the_rows_that_reject_a_case(tmp_path):
    from leak_check import drop, fp, norm_cmd
    lines, sh = fp("a b c d e\nf g h i j")
    cp = {"id": "c", "cmds": [norm_cmd("pytest -q")], "reps": [{"lines": sorted(lines), "shingles": sorted(sh)}]}
    prints = tmp_path / "prints.json"
    prints.write_text(json.dumps([cp]))
    rows = [{"messages": [{"role": "user", "content": "Commande : pytest -q\na b c d e\nf g h i j"}]},
            {"messages": [{"role": "user", "content": "Commande : ls\nautre chose\nrien à voir"}]}]
    src, out = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    src.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert drop(prints, src, out) == {"rows": 2, "dropped": 1, "kept": 1, "cases": ["c"]}
    assert [json.loads(l) for l in out.read_text().splitlines()] == rows[1:]
    assert not any(c["rejected"] for c in scan_texts([cp], examples_from_jsonl(out))["cases"])
