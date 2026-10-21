"""Tests de judge_useful_v3.py : prompt, lecture de la note, contrôles plantés, agrégats. Aucun réseau."""

import json
from pathlib import Path

import pytest

import judge_useful_v3 as ju

SUMMARY = {"id": "v3-x-0001", "task": "summary", "cmd": "ping -c 1 h", "exit": 0, "duration_s": 1.0,
           "output_raw": "1 packets transmitted, 1 received", "family": "network"}
QA = {"id": "v3-history-qa-0001", "task": "qa", "family": "history-qa", "cwd": "~/p",
      "question": {"fr": "Combien de tests ?", "en": "How many tests?"},
      "history": [{"cmd": "pytest", "exit": 1, "duration_s": 2.0, "output_raw": "2 failed, 7 passed"}]}


def test_summary_prompt_carries_raw_output_exit_code_and_language():
    msgs = ju.build_messages(SUMMARY, "en", "Host up.")
    assert msgs[0]["content"] == ju.SYSTEM
    user = msgs[1]["content"]
    assert "ping -c 1 h" in user and "1 packets transmitted, 1 received" in user
    assert "Code de sortie : 0" in user
    assert "anglais" in user
    assert user.rstrip().endswith("Host up.")


def test_qa_prompt_carries_history_and_question_in_its_language():
    user = ju.build_messages(QA, "fr", "2 échecs.")[1]["content"]
    assert "pytest" in user and "2 failed, 7 passed" in user and "code 1" in user
    assert "Combien de tests ?" in user and "How many tests?" not in user


def test_long_output_is_cut_in_the_middle():
    case = dict(SUMMARY, output_raw="A" * 20000 + "FIN")
    user = ju.build_messages(case, "fr", "x")[1]["content"]
    assert "FIN" in user and len(user) < 14000


@pytest.mark.parametrize("text,note,inv", [
    ('{"note": 75, "invention": false, "raison": "détail manquant"}', 75, False),
    ('```json\n{"note": 0, "invention": true, "raison": "ligne 4"}\n```', 0, True),
])
def test_parse_note(text, note, inv):
    r = ju.parse_note(text)
    assert r["note"] == note and r["invention"] is inv


@pytest.mark.parametrize("text", ['{"note": 60, "invention": false}', "rien", '{"invention": false}'])
def test_parse_note_off_scale_is_error(text):
    assert ju.parse_note(text)["note"] is None


def test_invention_forces_zero():
    assert ju.parse_note('{"note": 75, "invention": true, "raison": "r"}')["note"] == 0


def test_controls_report_counts_exact_and_adjacent():
    ctrl = [{"rung": 100}, {"rung": 75}, {"rung": 0}, {"rung": 50}]
    notes = [100, 50, 0, None]
    rep = ju.controls_report(ctrl, notes)
    assert rep == {"n": 4, "exact": 2, "adjacent": 3, "errors": 1, "by_rung": {"0": [0], "50": [None], "75": [50],
                                                                               "100": [100]}}


def test_aggregate_per_run():
    rows = [{"id": "a@fr", "note": 100, "invention": False}, {"id": "b@en", "note": 50, "invention": False},
            {"id": "c@fr", "note": 0, "invention": True}, {"id": "d@fr", "note": None, "invention": None}]
    agg = ju.aggregate(rows, {"a": "summary", "b": "summary", "c": "qa", "d": "qa"})
    assert agg == {"useful": 50.0, "fr": 50.0, "en": 50.0, "summary": 75.0, "qa": 0.0, "inventions_pct": 33.3,
                   "n": 3, "errors": 1}


def test_controls_file_is_well_formed():
    ctrl = json.loads((Path(ju.__file__).parent / "useful_controls.json").read_text())
    assert len(ctrl) == 15
    for rung in ju.RUNGS:
        assert sum(c["rung"] == rung for c in ctrl) == 3


def test_refuses_test_split():
    with pytest.raises(SystemExit):
        ju.check_split("test")


def test_decision_test_opens_the_test_split_only_on_request():
    ju.check_split("dev")
    ju.check_split("test", decision_test=True)
    with pytest.raises(SystemExit):
        ju.check_split("train", decision_test=True)


def test_test_split_without_decision_flag_is_refused_by_the_cli(monkeypatch):
    monkeypatch.setattr("sys.argv", ["judge_useful_v3.py", "report", "--verdicts", "v.json", "--split", "test", "r.json"])
    with pytest.raises(SystemExit, match="TEST refusé"):
        ju.main()


def test_decision_trace_is_written_to_the_spend_ledger(tmp_path):
    ledger = ju.oc.Ledger(tmp_path / "spend.jsonl", 0.6)
    ju.decision_trace(ledger, "m/judge", ["/x/g5c-test-b7.json", "/x/a-sft-test-b7.json"])
    rec = json.loads((tmp_path / "spend.jsonl").read_text().splitlines()[0])
    assert rec["event"] == "decision-test" and rec["split"] == "test" and rec["cost"] == 0
    assert rec["model"] == "m/judge" and rec["runs"] == ["g5c-test-b7.json", "a-sft-test-b7.json"]
    assert ju.oc.Ledger(tmp_path / "spend.jsonl", 0.6).spent == 0
