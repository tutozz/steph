"""X3 : harnais v3 au format de production du profil générique (modèles bruts) : SUMMARY_SYSTEM,
sortie plafonnée à cfg.summary_chars, historique des questions au budget cfg.qa_budget_chars.
Mêmes lignes, mêmes ids et même reaches_model que le harnais affiné."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import generic_harness  # noqa: E402
import v3lib  # noqa: E402
from steph import prompts  # noqa: E402
from steph.config import Config  # noqa: E402

LOTS = sorted((Path(__file__).resolve().parents[1] / "cases").glob("L*.jsonl"))


def cases():
    return [json.loads(l) for p in LOTS for l in open(p) if l.strip()]


def longest(task, size):
    return max((c for c in cases() if c["task"] == task), key=size)


def test_summary_uses_generic_prompt_and_generic_cap():
    c = longest("summary", lambda c: len(c["output_raw"]))
    for lang, system in (("fr", prompts.SUMMARY_SYSTEM), ("en", prompts.SUMMARY_SYSTEM_EN)):
        msgs = generic_harness.summary_input(c, lang)
        assert msgs[0] == {"role": "system", "content": system}
        fine = v3lib.rebuild_summary_input(c, lang)
        assert msgs[1]["content"] != fine[1]["content"]
        assert len(msgs[1]["content"]) > len(fine[1]["content"])
        assert len(msgs[1]["content"]) < len(fine[1]["content"]) + Config().summary_chars


def test_qa_keeps_the_production_shape_with_the_generic_budget():
    c = longest("qa", lambda c: sum(len(h["output_raw"]) for h in c["history"]))
    fine = v3lib.rebuild_qa_input(c, "fr")
    msgs = generic_harness.qa_input(c, "fr")
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[0] == fine[0] and msgs[2:] == fine[2:]
    assert len(msgs[1]["content"]) > len(fine[1]["content"])
    assert len(msgs[1]["content"]) <= Config().qa_budget_chars + 200


def test_short_history_is_identical_to_the_finetuned_input():
    c = min((c for c in cases() if c["task"] == "qa"), key=lambda c: sum(len(h["output_raw"]) for h in c["history"]))
    assert generic_harness.qa_input(c, "en") == v3lib.rebuild_qa_input(c, "en")


def test_rows_mirror_the_finetuned_harness():
    fine = json.load(open(v3lib.V3 / "harness" / "dev.json"))
    rows = generic_harness.rows("dev")
    assert [r["id"] for r in rows] == [r["id"] for r in fine]
    for g, f in zip(rows, fine):
        assert set(g) == set(f)
        assert {k: v for k, v in g.items() if k != "messages"} == {k: v for k, v in f.items() if k != "messages"}
    assert all(r["messages"][0]["content"] in (prompts.SUMMARY_SYSTEM, prompts.SUMMARY_SYSTEM_EN)
               for r in rows if r["kind"] == "summary")
