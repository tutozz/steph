"""Tests of the G5 data helpers: PYTHONPATH=src python3 -m pytest bench/matrix/finetune/g5/test_g5_data.py

SPDX-License-Identifier: MIT
"""

import json

import hashlib

from g5_data import distill_rows, key, qa_present_pairs

SYS_FR = "Tu résumes."
SYS_EN = "You summarize."


def row(source, user, label, system=SYS_FR):
    return {"source": source, "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user},
                                           {"role": "assistant", "content": label}]}


def v(*triples):
    return {key(ctx, phrase): verdict for ctx, phrase, verdict in triples}


def gen(idx, out, split="train", seed=42):
    return {"split": split, "idx": idx, "seed": seed, "temperature": 0.0, "out": out}


# --- qa_present_pairs -------------------------------------------------------------------------

def test_abstention_on_present_question_becomes_rejected():
    rows = [row("qa", "Q: quel port ?", "Le port 8080.")]
    pairs, counts = qa_present_pairs(rows, [gen(0, "Pas dans l'historique.")], {}, 3)
    assert pairs == [{"prompt": rows[0]["messages"][:-1], "chosen": "Le port 8080.", "rejected": "Pas dans l'historique."}]
    assert counts["abstention"] == 1


def test_invention_on_present_question_becomes_rejected():
    rows = [row("qa_en", "Q: which port?", "Port 8080.", SYS_EN)]
    verdicts = v(("Q: which port?", "Port 9090.", "invention"))
    pairs, _ = qa_present_pairs(rows, [gen(0, "Port 9090.")], verdicts, 3)
    assert [p["rejected"] for p in pairs] == ["Port 9090."]


def test_absent_question_gives_no_pair():
    rows = [row("qa", "Q: quel port ?", "Pas dans l'historique.")]
    verdicts = v(("Q: quel port ?", "Le port 22.", "invention"))
    pairs, counts = qa_present_pairs(rows, [gen(0, "Le port 22.")], verdicts, 3)
    assert pairs == [] and counts["absent_rows"] == 1


def test_summaries_give_no_pair_even_when_invented():
    rows = [row("fr_summary", "Commande : ls", "Liste des fichiers.")]
    verdicts = v(("Commande : ls", "Trois fichiers.", "invention"))
    pairs, _ = qa_present_pairs(rows, [gen(0, "Trois fichiers.")], verdicts, 3)
    assert pairs == []


def test_ok_or_doubtful_answers_are_not_rejected():
    rows = [row("qa", "Q: quel port ?", "Le port 8080.")]
    verdicts = v(("Q: quel port ?", "8080.", "ok"), ("Q: quel port ?", "Port 8080 ou 80.", "douteux"))
    pairs, _ = qa_present_pairs(rows, [gen(0, "8080."), gen(0, "Port 8080 ou 80.", seed=7)], verdicts, 3)
    assert pairs == []


def test_duplicates_and_cap_per_prompt():
    rows = [row("qa", "Q: quel port ?", "Le port 8080.")]
    outs = ["Pas dans l'historique.", "Pas dans l'historique.", "Pas dans l'historique : rien.",
            "Introuvable dans l'historique.", "Not in the history."]
    pairs, _ = qa_present_pairs(rows, [gen(0, o, seed=s) for s, o in enumerate(outs)], {}, 3)
    assert [p["rejected"] for p in pairs] == [outs[0], outs[2], outs[3]]


# --- distill_rows -----------------------------------------------------------------------------

def test_ok_teacher_output_replaces_label():
    rows = [row("fr_summary", "Commande : ls", "Liste des fichiers du dossier.")]
    verdicts = v(("Commande : ls", "Le dossier contient des fichiers.", "ok"))
    out, counts = distill_rows(rows, {0: "Le dossier contient des fichiers."}, verdicts)
    assert out[0]["messages"][-1]["content"] == "Le dossier contient des fichiers."
    assert out[0]["messages"][:-1] == rows[0]["messages"][:-1]
    assert out[0]["source"] == "fr_summary" and counts["replaced"] == 1


def test_invented_or_doubtful_teacher_output_keeps_label():
    rows = [row("fr_summary", "Commande : ls", "Liste."), row("fr_summary", "Commande : df", "Disque.")]
    verdicts = v(("Commande : ls", "Trois fichiers.", "invention"), ("Commande : df", "Disque plein à 90 %.", "douteux"))
    out, counts = distill_rows(rows, {0: "Trois fichiers.", 1: "Disque plein à 90 %."}, verdicts)
    assert [r["messages"][-1]["content"] for r in out] == ["Liste.", "Disque."]
    assert counts["invention"] == 1 and counts["douteux"] == 1


def test_missing_teacher_output_keeps_label():
    rows = [row("fr_summary", "Commande : ls", "Liste.")]
    out, counts = distill_rows(rows, {}, {})
    assert out == rows and counts["no_output"] == 1


def test_teacher_in_the_other_language_keeps_label():
    rows = [row("en_summary", "Command: ls\nOutput:\nfichier", "The folder holds one file.", SYS_EN)]
    text = "Le dossier contient un seul fichier dans le répertoire."
    verdicts = v(("Command: ls\nOutput:\nfichier", text, "ok"))
    out, counts = distill_rows(rows, {0: text}, verdicts)
    assert out[0]["messages"][-1]["content"] == "The folder holds one file." and counts["language"] == 1


def test_abstention_must_match_on_questions():
    rows = [row("qa", "Q: quel port ?", "Pas dans l'historique."), row("qa", "Q: quelle version ?", "La version 3.12.")]
    verdicts = v(("Q: quel port ?", "Le port 22.", "ok"), ("Q: quelle version ?", "Pas dans l'historique.", "ok"))
    out, counts = distill_rows(rows, {0: "Le port 22.", 1: "Pas dans l'historique."}, verdicts)
    assert [r["messages"][-1]["content"] for r in out] == ["Pas dans l'historique.", "La version 3.12."]
    assert counts["abstention_mismatch"] == 2


def test_key_is_the_judge_outputs_key():
    assert key("c", "p") == hashlib.sha256("c\x00p".encode()).hexdigest()


def test_rows_are_json_serialisable():
    rows = [row("qa", "Q: quel port ?", "Le port 8080.")]
    out, _ = distill_rows(rows, {0: "Port 8080."}, v(("Q: quel port ?", "Port 8080.", "ok")))
    json.dumps(out, ensure_ascii=False)
