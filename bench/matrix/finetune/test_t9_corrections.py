"""Tests des parties pures de t9_corrections.py : tirage, verdict de l'enseignant, paires. Aucun réseau."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import t9_corrections as tc  # noqa: E402


def row(user, label, system="TRAIN", **extra):
    return {"source": "s", **extra, "messages": [{"role": "system", "content": system},
                                                 {"role": "user", "content": user},
                                                 {"role": "assistant", "content": label}]}


def qa_row(q, label, category):
    return {"source": "qa-synth", "_category": category, "messages": [
        {"role": "system", "content": "QA"}, {"role": "user", "content": "ctx"},
        {"role": "assistant", "content": "ok"}, {"role": "user", "content": q},
        {"role": "assistant", "content": label}]}


def write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def test_items_dedupe_and_order_qa_first(tmp_path):
    final = tmp_path / "final"
    final.mkdir()
    write(final / "macos.jsonl", [row("a", "A"), row("b", "B")])
    write(final / "linux-dev.jsonl", [row("a", "A2")])
    write(final / "macos.en.jsonl", [row("e", "E")])
    write(final / "detail.jsonl", [row("d", "D")])
    qa = tmp_path / "qa.jsonl"
    write(qa, [qa_row("q1", "Oui", "present"), qa_row("q2", "Pas dans l'historique.", "absent")])
    items = tc.build_items(final, qa)
    assert [(i["task"], i["lang"]) for i in items] == [("qa", "fr"), ("qa", "fr"), ("summary", "fr"), ("summary", "fr"),
                                                     ("summary", "en")]
    assert items[0]["prompt"][-1]["content"] == "q1"
    assert items[0]["category"] == "present"
    assert items[2]["prompt"] == [{"role": "system", "content": "TRAIN"}, {"role": "user", "content": "a"}]


def test_parse_verdict_accepts_json_with_noise():
    v = tc.parse_verdict('```json\n{"verdict": "invention", "raison": "ligne 42", "correction": "Échec. main.c."}\n```')
    assert v == {"verdict": "invention", "raison": "ligne 42", "correction": "Échec. main.c."}


def test_parse_verdict_rejects_unknown_verdict():
    assert tc.parse_verdict('{"verdict": "peut-être"}')["verdict"] == "erreur"
    assert tc.parse_verdict("pas de json")["verdict"] == "erreur"


def test_pair_only_for_faulty_answer_with_clean_correction():
    item = {"iid": "x", "task": "summary", "lang": "fr", "category": None, "source_file": "macos",
            "prompt": [{"role": "system", "content": "TRAIN"}, {"role": "user", "content": "u"}]}
    ok = tc.make_pair(item, "v1.0", "Succès.", {"verdict": "ok", "correction": ""})
    assert ok is None
    bad = tc.make_pair(item, "v1.0", "Échec ligne 42.", {"verdict": "invention", "raison": "r",
                                                          "correction": "Échec. main.c, point-virgule manquant."})
    assert bad["rejected"] == "Échec ligne 42."
    assert bad["chosen"] == "Échec. main.c, point-virgule manquant."
    assert bad["sft"]["messages"][-1] == {"role": "assistant", "content": "Échec. main.c, point-virgule manquant."}
    assert bad["sft"]["messages"][:2] == item["prompt"]
    too_long = tc.make_pair(item, "v1.0", "x", {"verdict": "manque", "correction": " ".join(["mot"] * 40)})
    assert too_long is None
    same = tc.make_pair(item, "v1.0", "Échec.", {"verdict": "manque", "correction": "Échec."})
    assert same is None


def test_absent_question_correction_is_canonical():
    item = {"iid": "q", "task": "qa", "lang": "fr", "category": "absent", "source_file": "qa_train",
            "prompt": [{"role": "system", "content": "QA"}, {"role": "user", "content": "q"}]}
    p = tc.make_pair(item, "g3b", "3 fichiers.", {"verdict": "invention", "correction": "Rien sur ça."})
    assert p["chosen"] == "Pas dans l'historique."


def test_present_question_correction_cannot_abstain():
    item = {"iid": "q", "task": "qa", "lang": "fr", "category": "present", "source_file": "qa_train",
            "prompt": [{"role": "system", "content": "QA"}, {"role": "user", "content": "q"}]}
    p = tc.make_pair(item, "g3b", "Pas dans l'historique.", {"verdict": "abstention",
                                                             "correction": "Pas dans l'historique."})
    assert p is None
    p = tc.make_pair(item, "g3b", "Pas dans l'historique.", {"verdict": "abstention", "correction": "Code 0, succès."})
    assert p["chosen"] == "Code 0, succès."
