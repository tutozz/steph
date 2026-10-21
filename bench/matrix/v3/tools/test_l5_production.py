"""L5 actif en production (commit 20cfa0d) : le banc v3 envoie au modèle l'entrée de steph, bloc de
faits compris, pour les profils affiné et générique. Les harnais d'avant L5 restent dans harness/pre-l5/."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import build_inputs  # noqa: E402
import facts_harness  # noqa: E402
import generic_harness  # noqa: E402
import v3lib  # noqa: E402
from steph.config import Config  # noqa: E402
from steph.digest import extract_facts  # noqa: E402
from steph.narrator import Narrator  # noqa: E402
from steph.session import Session  # noqa: E402
from steph.strings import t  # noqa: E402

PRE_L5 = v3lib.V3 / "harness" / "pre-l5"


class _Speaker:
    def say(self, text, interrupt=True, on_done=None):
        if on_done:
            on_done(text)

    def say_stream(self, pieces, interrupt=True, on_done=None):
        self.say("".join(pieces), interrupt, on_done)

    def stop(self):
        pass


def narrator_input(case, lang, profile):
    """Messages que Narrator._finish passe au modèle pour ce cas, ou None s'il répond sans modèle."""
    n = Narrator(Config(language=lang, llm_profile=profile), Session(), _Speaker(), None)
    sent = []
    n._llm_say = lambda msgs, *a, **k: sent.append(msgs)
    c = n.s.start(case["cmd"])
    # départ à 0 pour que end - start rende la durée à l'identique (1 + 0,85 - 1 s'arrondit à 0,9) ;
    # end nul voudrait dire « en cours », d'où un epsilon pour une durée nulle
    c.start = c.enter_at = 0.0
    c.end, c.exit = case["duration_s"] or 1e-9, case["exit"]
    c.out.lines = v3lib.output_lines(case["output_raw"])
    c.out.total_lines = case["nlines"]
    n._finish(c, c.cwd, c.cwd)
    return sent[0] if sent else None


def split_cases(split):
    return sorted((json.loads(l) for p in sorted((v3lib.V3 / "cases" / split).glob("*.jsonl"))
                   for l in open(p) if l.strip()), key=lambda c: c["id"])


@pytest.fixture(scope="module")
def dev_summaries():
    return [c for c in split_cases("dev") if c["task"] == "summary"]


@pytest.mark.parametrize("profile,build", [("finetuned", v3lib.rebuild_summary_input),
                                           ("generic", generic_harness.summary_input)])
def test_summary_input_is_what_the_narrator_sends(dev_summaries, profile, build):
    compared = with_facts = 0
    for c in dev_summaries:
        for lang in ("fr", "en"):
            sent = narrator_input(c, lang, profile)
            if sent is None:
                continue
            compared += 1
            with_facts += t(lang, "facts.header") in sent[1]["content"]
            assert build(c, lang) == sent, f"{c['id']}@{lang}"
    # D6 dit en code environ 80 % des résumés DEV : 147 entrées atteignent encore le modèle
    assert compared > 120 and with_facts > 40


@pytest.mark.parametrize("split", ["dev", "test"])
def test_cases_carry_the_production_summary_input(split):
    for c in split_cases(split):
        if c["task"] == "summary":
            for lang in ("fr", "en"):
                assert c["input"][lang] == v3lib.rebuild_summary_input(c, lang), f"{c['id']}@{lang}"


@pytest.mark.parametrize("split", ["dev", "test"])
def test_harness_rows_are_the_case_inputs(split):
    inputs = {f"{c['id']}@{lang}": c["input"][lang] for c in split_cases(split) for lang in ("fr", "en")}
    rows = json.load(open(v3lib.V3 / "harness" / f"{split}.json"))
    assert len(rows) == len(inputs)
    assert all(r["messages"] == inputs[r["id"]] for r in rows)


@pytest.mark.parametrize("split", ["dev", "test"])
def test_new_harnesses_are_the_pre_l5_ones_plus_the_facts_block(split):
    fine = facts_harness.rows("finetuned", split, json.load(open(PRE_L5 / f"{split}.json")))
    assert fine == json.load(open(v3lib.V3 / "harness" / f"{split}.json"))
    generic = facts_harness.rows("generic", split, json.load(open(PRE_L5 / f"{split}.generic.json")))
    assert generic == generic_harness.rows(split)


def test_build_inputs_rewrites_a_stale_summary_input_and_nothing_else(dev_summaries):
    c = next(c for c in dev_summaries
             if extract_facts(c["cmd"], c["exit"], "\n".join(v3lib.output_lines(c["output_raw"])), "fr"))
    stale = json.loads(json.dumps(c))
    for lang in ("fr", "en"):
        user = stale["input"][lang][1]["content"]
        start = user.index(t(lang, "facts.header"))
        end = user.index("\nSortie :\n" if lang == "fr" else "\nOutput:\n", start) + 1
        stale["input"][lang][1]["content"] = user[:start] + user[end:]
    stale["input"]["builder"]["steph_commit"] = "58a0917"
    out = build_inputs.rebuild(stale, "20cfa0d")
    assert out["input"]["fr"] == c["input"]["fr"] and out["input"]["en"] == c["input"]["en"]
    assert out["input"]["builder"] == {**c["input"]["builder"], "steph_commit": "20cfa0d"}
    assert {k: v for k, v in out.items() if k != "input"} == {k: v for k, v in c.items() if k != "input"}
