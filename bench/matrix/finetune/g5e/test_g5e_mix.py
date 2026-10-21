"""Tests de g5e_mix.py sur un mélange synthétique (aucune donnée du corpus).

    PYTHONPATH=bench/matrix/results/finetune/loop/round-3/r3t2p3 python3 -m pytest bench/matrix/finetune/g5e/test_g5e_mix.py
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANG = HERE.parents[1] / "results/finetune/loop/round-3/r3t2p3"
SYS_FR = "Tu résumes la sortie de la commande pour une personne qui ne voit pas l'écran, en une phrase."
SYS_EN = "You summarize the output of the command for a person who cannot see the screen, in one sentence."
FR = "La compilation a échoué dans le fichier main.c à la ligne 3."
EN = "The build failed in the file main.c at line 3."
UNDECIDED = "make: 3"


def row(source, system, user, label):
    return json.dumps({"source": source, "messages": [{"role": "system", "content": system},
                                                      {"role": "user", "content": user},
                                                      {"role": "assistant", "content": label}]}, ensure_ascii=False)


def write(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")


def run(tmp_path, train, val=(), x4=(), extra=()):
    write(tmp_path / "mix/train.jsonl", train)
    write(tmp_path / "mix/val.jsonl", list(val) or [row("fr_summary", SYS_FR, "v", FR)])
    write(tmp_path / "x4/macos.jsonl", list(x4) or [row("macos", SYS_FR, "zz", FR)])
    write(tmp_path / "extra/train.jsonl", list(extra) or [row("qa", SYS_FR, "qq", FR)])
    write(tmp_path / "extra/val.jsonl", [row("qa", SYS_FR, "qv", FR)])
    out = subprocess.run([sys.executable, str(HERE / "g5e_mix.py"), str(tmp_path / "mix"), str(tmp_path / "x4"),
                          str(tmp_path / "extra"), str(tmp_path / "out")], capture_output=True, text=True, check=True,
                         env={"PYTHONPATH": str(LANG)})
    lines = (tmp_path / "out/train.jsonl").read_text(encoding="utf-8").splitlines()
    return json.loads(out.stdout), [json.loads(l)["messages"][-1]["content"] for l in lines], lines


def test_wrong_language_label_takes_x4_label(tmp_path):
    rep, labels, _ = run(tmp_path, [row("fr_summary", SYS_FR, "u1", EN)], x4=[row("macos", SYS_FR, "u1", FR)])
    assert labels == [FR] and rep["train"]["relabeled"] == 1


def test_undecided_label_is_kept(tmp_path):
    _, labels, _ = run(tmp_path, [row("fr_summary", SYS_FR, "u1", UNDECIDED)], x4=[row("macos", SYS_FR, "u1", FR)])
    assert labels == [UNDECIDED]


def test_x4_label_in_the_same_wrong_language_is_not_taken(tmp_path):
    rep, labels, _ = run(tmp_path, [row("detail", SYS_FR, "u1", EN)], x4=[row("detail", SYS_FR, "u1", "The build failed.")])
    assert labels == [EN] and rep["detail"]["train_wrong_x4_also_wrong"] == {"detail": 1}


def test_x4_pairing_needs_the_same_system_prompt(tmp_path):
    _, labels, _ = run(tmp_path, [row("fr_summary", SYS_FR, "u1", EN)], x4=[row("macos.en", SYS_EN, "u1", FR)])
    assert labels == [EN]


def test_mix_extra_rows_never_change(tmp_path):
    extra = row("qa", SYS_FR, "u1", EN)
    _, labels, _ = run(tmp_path, [extra], x4=[row("macos", SYS_FR, "u1", FR)], extra=[extra])
    assert labels == [EN]


def test_english_prompt_corrections_are_tripled_at_the_end(tmp_path):
    train = [row("fr_summary", SYS_FR, "a", FR), row("t9-corr-v1.0", SYS_EN, "b", EN), row("t9-corr-g3b", SYS_FR, "c", FR)]
    rep, _, lines = run(tmp_path, train)
    assert lines[:3] == train and lines[3:] == [train[1], train[1]]
    assert rep["train"]["en_prompt_pct_out"] == 60.0


def test_english_prompt_correction_with_french_label_is_not_copied(tmp_path):
    train = [row("t9-corr-v1.0", SYS_EN, "b", FR), row("t9-corr-v1.0", SYS_EN, "c", EN)]
    _, _, lines = run(tmp_path, train)
    assert lines == train + [train[1], train[1]]
