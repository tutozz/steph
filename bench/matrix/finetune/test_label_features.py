"""Tests des parties pures de label_features.py (H3a) : grille de rejet par mode,
garde-fou contre un fichier de features aux modes mélangés. Aucun réseau, aucun LLM."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from label_features import MODES, judge, run  # noqa: E402


def test_judge_rejects_leaked_think_tag():
    assert judge("<think>raisonnement</think> Échec.", 25) == (None, "think")


def test_judge_rejects_empty_after_cleaning():
    assert judge("   ", 25) == (None, "vide")


def test_judge_rejects_over_the_mode_word_cap():
    raw = " ".join(f"mot{i}" for i in range(15))
    assert judge(raw, 10) == (None, "trop long")


def test_judge_accepts_within_the_mode_word_cap():
    label, reason = judge("Échec. Fichier main.c ligne 12.", 10)
    assert reason == "ok"
    assert label == "Échec. Fichier main.c ligne 12."


def test_modes_cover_every_build_feature_corpus_mode():
    assert set(MODES) == {"detail", "start", "progress", "flux", "summary"}


def test_run_refuses_a_file_with_mixed_modes(tmp_path):
    infile = tmp_path / "mixed.jsonl"
    infile.write_text(
        json.dumps({"id": "a", "mode": "detail", "messages": []}) + "\n" +
        json.dumps({"id": "b", "mode": "start", "messages": []}) + "\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(infile=str(infile), mode="detail", out=str(tmp_path / "out.jsonl"),
                              port=1, parallel=1, max_tokens=1, timeout=1.0, presence_penalty=1.0)
    try:
        run(args)
        assert False, "run() aurait dû refuser le mélange de modes"
    except SystemExit as e:
        assert e.code == 2
    assert not (tmp_path / "out.jsonl").exists()


# ---------------------------------------------------------------- K3 : détail resserré

def _detail_row(row_id="d1"):
    from steph.prompts import DETAILS_SYSTEM
    return {"id": row_id, "mode": "detail",
            "messages": [{"role": "system", "content": DETAILS_SYSTEM},
                         {"role": "user", "content": "Commande : make\nStatut : échec (code 2)\nSortie :\nerror: x"}]}


def test_detail_teacher_prompt_no_longer_asks_what_to_do():
    from label_features import teacher_messages
    system = teacher_messages(_detail_row(), "detail")[0]["content"]
    assert "ce qu'il faut faire" not in system
    assert "cause" in system and "n'écrit pas" in system


def test_detail_prompts_do_not_force_a_minimum_of_three_points():
    from label_features import TRAIN_DETAILS_SYSTEM, teacher_messages
    for system in (TRAIN_DETAILS_SYSTEM, teacher_messages(_detail_row(), "detail")[0]["content"]):
        assert "3 à 5" not in system


def test_train_details_prompt_forbids_an_unwritten_cause():
    from label_features import TRAIN_DETAILS_SYSTEM
    assert "cause" in TRAIN_DETAILS_SYSTEM and "n'écrit pas" in TRAIN_DETAILS_SYSTEM


def test_teacher_messages_keep_the_user_turn_and_leave_other_modes_untouched():
    from label_features import teacher_messages
    row = _detail_row()
    assert teacher_messages(row, "detail")[1] == row["messages"][1]
    start = {"id": "s1", "mode": "start", "messages": [{"role": "system", "content": "x"},
                                                       {"role": "user", "content": "ls"}]}
    assert teacher_messages(start, "start") == start["messages"]


def test_run_sends_the_teacher_prompt_and_trains_on_the_short_prompt(tmp_path, monkeypatch):
    import label_features
    sent = []

    def fake_query(port, messages, max_tokens, timeout, presence_penalty):
        sent.append(messages)
        return "error: x."

    monkeypatch.setattr(label_features, "query", fake_query)
    infile = tmp_path / "detail.jsonl"
    infile.write_text(json.dumps(_detail_row(), ensure_ascii=False) + "\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    args = argparse.Namespace(infile=str(infile), mode="detail", out=str(out),
                              port=1, parallel=1, max_tokens=1, timeout=1.0, presence_penalty=1.0)
    label_features.run(args)
    assert sent[0][0]["content"] == label_features.teacher_messages(_detail_row(), "detail")[0]["content"]
    written = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert written["train_messages"][0]["content"] == label_features.TRAIN_DETAILS_SYSTEM


def test_detail_prompts_ask_for_useful_facts_without_the_header_metadata():
    from label_features import TRAIN_DETAILS_SYSTEM, teacher_messages
    for system in (TRAIN_DETAILS_SYSTEM, teacher_messages(_detail_row(), "detail")[0]["content"]):
        assert "ni la durée" in system
        assert "pas la sortie entière" in system


# ---------------------------------------------------------------- R1 : détail, début et progression en anglais

def _en_row(mode, system, user):
    return {"id": f"{mode}-en", "mode": mode, "messages": [{"role": "system", "content": system},
                                                           {"role": "user", "content": user}]}


def test_english_training_prompts_mirror_the_french_ones():
    from label_features import MODES, MODES_BY_LANG, TRAIN_DETAILS_SYSTEM_EN, TRAIN_PROGRESS_SYSTEM_EN, TRAIN_START_SYSTEM_EN
    from label import TRAIN_SYSTEM_EN
    en = MODES_BY_LANG["en"]
    assert MODES_BY_LANG["fr"] is MODES
    assert en["detail"] == (TRAIN_DETAILS_SYSTEM_EN, 60)
    assert en["start"] == (TRAIN_START_SYSTEM_EN, 10)
    assert en["progress"] == (TRAIN_PROGRESS_SYSTEM_EN, 12)
    assert en["summary"] == (TRAIN_SYSTEM_EN, 25)
    assert "in English" in TRAIN_DETAILS_SYSTEM_EN and "does not write" in TRAIN_DETAILS_SYSTEM_EN
    assert "in English" in TRAIN_START_SYSTEM_EN and "in English" in TRAIN_PROGRESS_SYSTEM_EN


def test_french_training_prompts_are_still_the_production_ones():
    from steph import prompts
    from label_features import MODES
    assert MODES["detail"][0] == prompts.DETAILS_SYSTEM_FINETUNED
    assert MODES["start"][0] == prompts.START_SYSTEM_FINETUNED
    assert MODES["progress"][0] == prompts.PROGRESS_SYSTEM_FINETUNED


def test_english_detail_teacher_prompt_is_english_and_other_modes_untouched():
    from steph.prompts import DETAILS_SYSTEM_EN, START_SYSTEM_EN
    from label_features import TEACHER_DETAILS_SYSTEM_EN, teacher_messages
    row = _en_row("detail", DETAILS_SYSTEM_EN, "Command: make\nStatus: failure (code 2)\nOutput:\nerror: x")
    assert teacher_messages(row, "detail", "en")[0]["content"] == TEACHER_DETAILS_SYSTEM_EN
    assert "does not write" in TEACHER_DETAILS_SYSTEM_EN
    start = _en_row("start", START_SYSTEM_EN, "ls")
    assert teacher_messages(start, "start", "en") == start["messages"]


def test_run_in_english_trains_on_the_english_short_prompt(tmp_path, monkeypatch):
    import label_features
    from steph.prompts import START_SYSTEM_EN
    monkeypatch.setattr(label_features, "query", lambda *a: "List files.")
    infile = tmp_path / "start.en.jsonl"
    infile.write_text(json.dumps(_en_row("start", START_SYSTEM_EN, "ls")) + "\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    args = argparse.Namespace(infile=str(infile), mode="start", out=str(out), lang="en",
                              port=1, parallel=1, max_tokens=1, timeout=1.0, presence_penalty=1.0)
    label_features.run(args)
    written = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert written["train_messages"][0]["content"] == label_features.TRAIN_START_SYSTEM_EN
    assert written["train_messages"][1]["content"] == "ls"
