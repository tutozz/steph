import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench/matrix/finetune"))

from label import TRAIN_SYSTEM, build_messages  # noqa: E402
from rebuild_p15 import header_key, loses_fact, match_raw, rebuild_row, strip_status  # noqa: E402

SCRIPT = ROOT / "bench/matrix/finetune/rebuild_p15.py"


def raw(cmd="ls /srv", exit_code=0, duration=0.2, output="a.txt\nb.txt\nc.txt\n"):
    return {"cmd": cmd, "exit": exit_code, "duration": duration, "output": output}


def old_row(rec, label, max_chars=1500):
    return {"messages": build_messages(rec, max_chars) + [{"role": "assistant", "content": label}]}


def test_strip_status_removes_the_word_p9_already_says():
    assert strip_status("Échec. main.rs ligne 3 : type attendu.") == "main.rs ligne 3 : type attendu."
    assert strip_status("Succès. Fichier créé.") == "Fichier créé."
    assert strip_status("Échec, code 2 : introuvable.") == "introuvable."


def test_strip_status_leaves_labels_without_status_word():
    assert strip_status("Copie réussie.") == "Copie réussie."
    assert strip_status("Échecs de connexion : 3.") == "Échecs de connexion : 3."


def test_strip_status_of_a_bare_status_is_empty():
    assert strip_status("Succès.") == ""


def test_loses_fact_when_the_label_cites_a_file_absent_from_the_input():
    user = "Commande : ls\nStatut : succès (code 0)\nSortie :\na.txt\nb.txt"
    assert loses_fact(user, "Trois fichiers, dont c.txt.")
    assert not loses_fact(user, "Fichiers a.txt et b.txt.")


def test_loses_fact_when_a_number_is_only_in_the_exit_code():
    user = "Commande : false\nStatut : échec (code 3)\nSortie :\nboom"
    assert loses_fact(user, "Code 3.")


def test_qa_answer_not_in_history_is_kept():
    user = "Historique de la session :\n[1] ? $ ls\na.txt\n\nQuestion : quelle version de Python ?"
    assert not loses_fact(user, "Pas dans l'historique.")


def test_match_raw_uses_the_header_then_the_output_to_break_ties():
    first, second = raw(output="x.txt\n"), raw(output="y.txt\n")
    index = {}
    for rec in (first, second):
        index.setdefault(header_key(build_messages(rec, 1500)[1]["content"]), []).append(rec)
    row = old_row(second, "Un fichier.")
    assert match_raw(row["messages"][1]["content"], index) is second


def test_match_raw_returns_none_for_an_unknown_command():
    assert match_raw(old_row(raw(cmd="uptime"), "Up.")["messages"][1]["content"], {}) is None


def test_rebuild_row_uses_train_system_new_budget_and_stripped_label():
    output = "".join(f"ligne numéro {i} du journal de service\n" for i in range(200))
    rec = raw(cmd="journalctl -n 200", exit_code=1, output=output)
    new = rebuild_row(old_row(rec, "Échec. Journal de 200 lignes."), rec, 300)
    assert new["messages"][0] == {"role": "system", "content": TRAIN_SYSTEM}
    assert new["messages"][1] == build_messages(rec, 300)[1]
    assert new["messages"][2] == {"role": "assistant", "content": "Journal de 200 lignes."}
    assert len(new["messages"][1]["content"]) < len(build_messages(rec, 1500)[1]["content"])


def test_cli_drops_labels_that_lose_a_fact_and_keeps_qa(tmp_path):
    kept = raw(cmd="ls /srv", output="a.txt\nb.txt\n")
    lost = raw(cmd="ls /opt", output="".join(f"f{i}.log\n" for i in range(400)))
    mix = tmp_path / "mix"
    mix.mkdir()
    (mix / "train.jsonl").write_text(json.dumps(old_row(kept, "Succès. a.txt et b.txt.")) + "\n"
                                     + json.dumps(old_row(lost, "Fichier f10.log présent.")) + "\n")
    (mix / "val.jsonl").write_text("")
    raw_file = tmp_path / "raw.jsonl"
    raw_file.write_text(json.dumps(kept) + "\n" + json.dumps(lost) + "\n")
    qa = tmp_path / "qa.jsonl"
    qa.write_text(json.dumps({"source": "qa", "_key": "k", "messages": [
        {"role": "system", "content": "s"}, {"role": "user", "content": "Historique :\n[1] ? $ ls\na.txt"},
        {"role": "assistant", "content": "Compris."}, {"role": "user", "content": "Quel fichier ?"},
        {"role": "assistant", "content": "a.txt."}]}) + "\n")

    out = subprocess.run([sys.executable, str(SCRIPT), "--mix", str(mix), "--raw", str(raw_file), "--qa", str(qa),
                          "--max-chars", "200", "--out", str(tmp_path / "p15")],
                         capture_output=True, text=True, check=True).stdout

    rows = [json.loads(line) for name in ("train", "val") for line in (tmp_path / "p15" / f"{name}.jsonl").open()]
    labels = [r["messages"][-1]["content"] for r in rows]
    assert sorted(labels) == ["a.txt et b.txt.", "a.txt."]
    assert all(set(r) == {"messages"} for r in rows)
    counts = json.loads(out.strip().splitlines()[-1])
    assert counts["summary_kept"] == 1 and counts["summary_lost_fact"] == 1 and counts["qa_kept"] == 1


def test_match_raw_falls_back_to_word_overlap_when_the_digest_changed():
    first = raw(output="alpha.conf beta.conf\n")
    second = raw(output="gamma.conf delta.conf\n")
    index = {header_key(build_messages(first, 1500)[1]["content"]): [first, second]}
    user = header_key(build_messages(second, 1500)[1]["content"]) + "Sortie :\ngamma.conf (et 1 autre)"
    assert match_raw(user, index) is second


def test_match_raw_refuses_a_tie_between_different_outputs():
    first, second = raw(output="alpha.conf\n"), raw(output="gamma.conf\n")
    index = {header_key(build_messages(first, 1500)[1]["content"]): [first, second]}
    user = header_key(build_messages(first, 1500)[1]["content"]) + "Sortie :\nautre chose"
    assert match_raw(user, index) is None
