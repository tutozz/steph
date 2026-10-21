"""Score of steph's resolve() shortcut (src/steph/digest.py) on TermSpeak: no model, no server.

resolve() is deterministic and French-only; it only ever sees a finished command (cmd, exit
code, output), never a conversation history, so "qa" cases are out of its scope.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmark"
DATA = BENCH / "data" / "v1"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = load("termspeak_run", BENCH / "run.py")
score_resolve = load("termspeak_score_resolve", BENCH / "tools" / "score_resolve.py")
CONFIG = run.load_config(DATA)


def test_qa_cases_are_excluded_resolve_has_no_history():
    cases = run.load_cases(DATA, "fr", "test")
    rows = score_resolve.score_resolve(cases, CONFIG["scoring"])
    scored_ids = {r["id"] for r in rows}
    qa_ids = {c["id"] for c in cases if c["task"] == "qa"}
    assert scored_ids.isdisjoint(qa_ids)
    assert len(rows) == len(cases) - len(qa_ids)


def test_a_known_compile_case_scores_on_french_facts():
    cases = {c["id"]: c for c in run.load_cases(DATA, "fr", "test")}
    case = cases["build-gcc-undeclared"]
    row = score_resolve.score_resolve([case], CONFIG["scoring"])[0]
    assert row["score"] > 0
    assert "main.c" in (row["answer"] or "")


def test_result_is_reproducible_like_a_normal_run():
    result = score_resolve.run_lang("fr", "test", DATA, CONFIG)
    cases_by_id = {c["id"]: c for c in run.load_cases(DATA, "fr", "all")}
    rescored = run.rescore(result, cases_by_id, CONFIG["scoring"])
    assert rescored["summary"]["score"] == result["summary"]["score"]


def test_never_mixed_with_a_model_label():
    result = score_resolve.run_lang("en", "test", DATA, CONFIG)
    assert "resolve" in result["model"]["label"].lower()
    assert result["backend"]["name"] != "llama.cpp"
