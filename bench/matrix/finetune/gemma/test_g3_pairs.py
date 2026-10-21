"""Tests of the G3 DPO pairs: PYTHONPATH=src python3 -m pytest bench/matrix/finetune/gemma/test_g3_pairs.py

SPDX-License-Identifier: MIT
"""

from g3_pairs import cache_key, entry_pairs, generic_messages, split_val
from steph import prompts

PROMPT = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def entry(task="summary", label="3 fichiers.", lang="fr", eid="e1"):
    return {"id": eid, "task": task, "lang": lang, "messages": PROMPT, "label": label}


def out(text, k=0):
    return {"k": k, "text": text}


def verdicts(eid, finals):
    return {cache_key(eid, t): {"final": f, "inventions": []} for t, f in finals.items()}


def test_invented_output_is_rejected_against_the_27b_label():
    e = entry()
    v = verdicts("e1", {"5 fichiers.": "invention", "3 fichiers, ok.": "ok"})
    pairs = entry_pairs(e, [out("5 fichiers."), out("3 fichiers, ok.", 1)], v)
    assert [(p["chosen"], p["rejected"], p["kind"]) for p in pairs] == [("3 fichiers.", "5 fichiers.", "invention")]
    assert pairs[0]["prompt"] == PROMPT


def test_doubtful_or_unjudged_outputs_give_no_pair():
    e = entry()
    v = verdicts("e1", {"4 fichiers.": "douteux"})
    assert entry_pairs(e, [out("4 fichiers."), out("jamais jugé", 1)], v) == []


def test_at_most_max_pairs_distinct_rejected():
    e = entry()
    texts = ["a1.", "a2.", "a3."]
    v = verdicts("e1", {t: "invention" for t in texts})
    pairs = entry_pairs(e, [out(t, k) for k, t in enumerate(texts + ["a1."])], v, max_pairs=2)
    assert [p["rejected"] for p in pairs] == ["a1.", "a2."]


def test_output_equal_to_label_is_never_rejected():
    e = entry()
    v = verdicts("e1", {"3 fichiers.": "invention"})
    assert entry_pairs(e, [out("3 fichiers.")], v) == []


def test_present_answer_question_gets_an_abstention_pair_even_without_on_policy_error():
    e = entry(task="qa", label="Cat : permission refusée.")
    pairs = entry_pairs(e, [out("Cat : permission refusée.")], {})
    assert [(p["rejected"], p["kind"]) for p in pairs] == [("Pas dans l'historique.", "abstention")]


def test_on_policy_abstention_on_present_answer_is_used_as_rejected():
    e = entry(task="qa", label="Port 8080.", lang="en")
    pairs = entry_pairs(e, [out("Not in the history.")], {})
    assert [(p["rejected"], p["kind"]) for p in pairs] == [("Not in the history.", "abstention")]


def test_absent_answer_question_never_gets_an_abstention_pair():
    e = entry(task="qa", label="Pas dans l'historique.")
    v = verdicts("e1", {"Port 22.": "invention"})
    pairs = entry_pairs(e, [out("Pas dans l'historique."), out("Port 22.", 1)], v)
    assert [(p["chosen"], p["rejected"]) for p in pairs] == [("Pas dans l'historique.", "Port 22.")]


def test_validation_split_is_by_entry_and_stable():
    pairs = [{"id": f"e{i}"} for i in range(400)] + [{"id": "e0"}]
    train, val = split_val(pairs, 0.1)
    assert len(train) + len(val) == len(pairs)
    assert 20 < len(val) < 70
    assert {p["id"] for p in train}.isdisjoint({p["id"] for p in val})
    assert split_val(pairs, 0.1) == (train, val)


def test_generic_prompt_keeps_the_facts_block_of_the_row():
    rec = {"cmd": "./run.sh", "exit": 1, "duration": 0.5, "nlines": 2, "output": "x\n./run.sh: line 3: y: unbound variable",
           "facts": ["Erreur du script : run.sh ligne 3 : y: unbound variable"]}
    msgs = generic_messages(rec, "fr")
    assert msgs == prompts.summary_messages(rec["cmd"], 1, 0.5, rec["output"], 2, language="fr", facts=rec["facts"])
    assert generic_messages({**rec, "facts": None}, "fr")[1]["content"].count("Faits extraits") == 0
