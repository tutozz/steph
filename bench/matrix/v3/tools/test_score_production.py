"""Tests of the composite production score (score_production.py): code answer when steph has one,
model answer otherwise, through the grounding guard and the status said in code.

    python3 -m pytest bench/matrix/v3/tools/test_score_production.py -q

SPDX-License-Identifier: MIT
"""

import json

import score_production as sp

FACTS = {"need": [{"id": "x", "fr": [r"zzz"], "en": [r"zzz"]}], "never": []}


def case(**kw):
    base = {"id": "v3-x-0001", "task": "summary", "family": "files", "cmd": "mytool run", "exit": 0,
            "duration_s": 0.2, "nlines": 1, "output_raw": "", "max_words": 20, "facts": FACTS}
    base.update(kw)
    return base


LONG_OUT = "\n".join(f"line {i} of some verbose output from the tool here" for i in range(30))


def test_empty_success_is_said_ok_in_code():
    assert sp.code_answer(case(), "fr") == "OK."


def test_empty_failure_says_code():
    assert sp.code_answer(case(exit=2), "en") == "Failed, code 2, no message."


def test_command_not_found_127():
    c = case(cmd="foo --x", exit=127, output_raw="zsh: command not found: foo")
    assert sp.code_answer(c, "en") == "Command not found: foo."


def test_short_output_read_verbatim_with_error_code():
    c = case(exit=1, output_raw="cannot open file\nabort", nlines=2)
    assert sp.code_answer(c, "fr") == "Erreur 1 : cannot open file. abort"


def test_short_output_read_verbatim_without_symbol_runs():
    c = case(cmd="make", exit=2, output_raw="make: *** No targets specified. Stop.", nlines=1)
    assert sp.code_answer(c, "en") == "Error 2: make: No targets specified. Stop."


def test_resolve_answers_in_code():
    out = "\n".join(["collected 5 items", "", "tests/test_a.py ..F..", "FAILED tests/test_a.py::test_merge - assert 1 == 2",
                     "=========== 1 failed, 4 passed in 0.12s ==========="] + ["noise line number %d with words" % i for i in range(10)])
    c = case(cmd="pytest -q", exit=1, output_raw=out, nlines=15)
    said = sp.code_answer(c, "en")
    assert said and "test_merge" in said


def test_long_output_goes_to_model():
    assert sp.code_answer(case(output_raw=LONG_OUT, nlines=30), "fr") is None


def test_model_answer_gets_status_prefix_and_loses_its_echo():
    c = case(exit=3, output_raw=LONG_OUT, nlines=30)
    text, src = sp.production_answer(c, "fr", "Échec. line 4 of some verbose output", "Sortie :\n" + LONG_OUT)
    assert src == "model"
    assert text.startswith("Échec, code 3. ")
    assert text.count("Échec") == 1


def test_grounding_drops_invented_number_clause():
    c = case(output_raw=LONG_OUT, nlines=30)
    text, _ = sp.production_answer(c, "en", "Done, line 4 printed, 9999 errors", LONG_OUT)
    assert "9999" not in text and "line 4" in text


def test_grounding_off_keeps_raw_model_text():
    c = case(output_raw=LONG_OUT, nlines=30)
    text, _ = sp.production_answer(c, "en", "Done, 9999 errors", LONG_OUT, ground=False)
    assert "9999" in text


def test_grounding_emptied_answer_says_fallback_summary():
    c = case(exit=1, output_raw=LONG_OUT, nlines=30)
    text, src = sp.production_answer(c, "en", "4242 errors", LONG_OUT)
    assert src == "model-fallback"
    assert text.startswith("Failed, code 1. ") and "Last line" in text


def test_only_echoed_status_surviving_grounding_says_fallback_summary():
    # narrator._llm_say : « Échec. » retiré par _drop_leading_status, flux vide, repli dit
    c = case(exit=1, output_raw=LONG_OUT, nlines=30)
    text, src = sp.production_answer(c, "en", "Failed. 4242 errors", LONG_OUT)
    assert src == "model-fallback"
    assert text.startswith("Failed, code 1. ") and "Last line" in text


def test_long_command_resolve_keeps_one_status():
    out = "\n".join(["collected 5 items", "FAILED tests/test_a.py::test_merge - assert 1 == 2",
                     "=========== 1 failed, 4 passed in 9.12s ==========="] + ["noise line number %d with words" % i for i in range(10)])
    c = case(cmd="pytest -q", exit=1, output_raw=out, nlines=13, duration_s=9.1)
    said = sp.code_answer(c, "en")
    assert said.startswith("Failed, code 1. ") and "Failed." not in said


def test_qa_grounding_says_not_in_history():
    q = {"id": "v3-history-qa-0001", "task": "qa", "family": "history-qa", "max_words": 30, "facts": FACTS}
    text, src = sp.production_answer(q, "fr", "4242 erreurs.", "Historique de la session :\n[1] ~ $ ls\nabc")
    assert src == "model" and text == "Pas dans l'historique."


def test_score_run_mixes_code_and_model(tmp_path):
    c_code = case(id="v3-x-0001", facts={"need": [{"id": "ok", "fr": [r"\bok\b"], "en": [r"\bok\b"]}], "never": []})
    c_model = case(id="v3-x-0002", output_raw=LONG_OUT, nlines=30,
                   facts={"need": [{"id": "l4", "fr": [r"line 4"], "en": [r"line 4"]}], "never": []})
    cases = {c["id"]: c for c in (c_code, c_model)}
    harness = {f"{cid}@fr": {"messages": [{"role": "user", "content": LONG_OUT}]} for cid in cases}
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"label": "m", "rows": [
        {"id": "v3-x-0001@fr", "out": "wrong model text"},
        {"id": "v3-x-0002@fr", "out": "line 4 shown"},
    ]}))
    res = sp.score_run(cases, str(run), harness)
    assert res["quality"] == 100.0
    assert res["code_share"] == 50.0
    assert res["per_case"]["v3-x-0001@fr"]["source"] == "code"


def test_127_inside_script_names_the_missing_program():
    c = case(cmd="bash deploy.sh", exit=127, output_raw="deploy.sh: line 7: rsyncx: command not found")
    assert sp.code_answer(c, "en") == "Command not found: rsyncx, deploy.sh line 7."


def test_grep_without_match_is_said_in_code():
    c = case(cmd="grep -rn DATABASE_URL config", exit=1)
    assert sp.code_answer(c, "fr") == "Aucune correspondance pour DATABASE_URL."
