"""X4 (P20) : l'entrée des questions du banc v3 est celle de la production, profil affiné :
système, historique, accusé, puis « (dossier actuel : …) » et la question."""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import v3lib  # noqa: E402
import validate  # noqa: E402

LOT = Path(__file__).resolve().parents[1] / "cases" / "L13.jsonl"


def first_qa():
    return next(c for c in map(json.loads, open(LOT)) if c["task"] == "qa")


def test_rebuild_is_the_production_shape():
    c = first_qa()
    msgs = v3lib.rebuild_qa_input(c, "fr")
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[1]["content"].startswith("Historique de la session :\n[1] " + c["cwd"] + " $ ")
    assert msgs[2]["content"] == "Compris, j'ai l'historique."
    assert msgs[3]["content"] == f"(dossier actuel : {c['cwd']})\n{c['question']['fr']}"
    en = v3lib.rebuild_qa_input(c, "en")
    assert en[2]["content"] == "Understood, I have the history."
    assert en[3]["content"] == f"(dossier actuel : {c['cwd']})\n{c['question']['en']}"


def test_validate_rejects_the_old_two_message_input():
    c = copy.deepcopy(first_qa())
    for lang in ("fr", "en"):
        m = v3lib.rebuild_qa_input(c, lang)
        c["input"][lang] = [m[0], {"role": "user", "content": m[1]["content"] + "\n\nQuestion : " + c["question"][lang]}]
    assert any("differs from src/steph" in e for e in validate.case_errors(c))


def test_validate_accepts_the_rebuilt_input():
    c = first_qa()
    assert validate.case_errors(c) == []


def test_judge_context_carries_history_and_question():
    import judge_v3
    c = first_qa()
    ctx = judge_v3.judge_context(v3lib.rebuild_qa_input(c, "fr"))
    assert ctx.startswith("Historique de la session :") and ctx.endswith(c["question"]["fr"])
    assert "Compris, j'ai l'historique." not in ctx
