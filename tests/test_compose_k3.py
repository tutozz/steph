import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench/matrix/finetune"))

from compose_k3 import (  # noqa: E402
    contaminated,
    header_key,
    long_lines,
    match_raw,
    rebuild_summary,
    speak_bench_lines,
    strip_status,
)
from label import TRAIN_SYSTEM, TRAIN_SYSTEM_EN, build_messages  # noqa: E402
from rebuild_p15 import rebuild_row  # noqa: E402

SCRIPT = ROOT / "bench/matrix/finetune/compose_k3.py"


def raw(cmd="ls /srv", exit_code=0, duration=0.2, output="a.txt\nb.txt\nc.txt\n"):
    return {"cmd": cmd, "exit": exit_code, "duration": duration, "output": output}


def labeled(rec, label, lang="fr", source="macos"):
    msgs = build_messages(rec, 1500, lang)
    return {"source": source, "messages": [msgs[0], msgs[1], {"role": "assistant", "content": label}]}


def test_strip_status_removes_english_status_words():
    assert strip_status("Failed. main.rs line 3: type expected.", "en") == "main.rs line 3: type expected."
    assert strip_status("Success. File created.", "en") == "File created."
    assert strip_status("Failed (code 2): not found.", "en") == "not found."
    assert strip_status("Successfully built 3 images.", "en") == "Successfully built 3 images."


def test_strip_status_keeps_the_french_behaviour():
    assert strip_status("Échec. main.rs ligne 3 : type attendu.", "fr") == "main.rs ligne 3 : type attendu."


def test_header_key_splits_on_the_marker_of_the_language():
    user = build_messages(raw(), 1500, "en")[1]["content"]
    assert header_key(user, "en").endswith("displayed\n")


def test_match_raw_finds_the_english_record_among_same_header_candidates():
    first, second = raw(output="x.txt\n"), raw(output="y.txt\n")
    index = {}
    for rec in (first, second):
        index.setdefault(header_key(build_messages(rec, 1500, "en")[1]["content"], "en"), []).append(rec)
    user = build_messages(second, 1500, "en")[1]["content"]
    assert match_raw(user, index, "en") is second


def test_rebuild_summary_english_uses_train_system_en_and_the_capped_english_input():
    output = "".join(f"service line number {i} of the journal\n" for i in range(200))
    rec = raw(cmd="journalctl -n 200", exit_code=1, output=output)
    new = rebuild_summary("Failed. Journal of 200 lines.", rec, 300, "en")
    assert new[0] == {"role": "system", "content": TRAIN_SYSTEM_EN}
    assert new[1] == build_messages(rec, 300, "en")[1]
    assert new[2] == {"role": "assistant", "content": "Journal of 200 lines."}


def test_rebuild_summary_french_matches_rebuild_p15():
    rec = raw(cmd="ls /opt", exit_code=0, output="a.txt\nb.txt\n")
    row = labeled(rec, "Succès. Deux fichiers, a.txt et b.txt.")
    assert rebuild_summary(row["messages"][2]["content"], rec, 587, "fr") == rebuild_row(row, rec, 587)["messages"]
    assert rebuild_summary("x", rec, 587, "fr")[0]["content"] == TRAIN_SYSTEM


def test_contaminated_needs_two_shared_long_lines():
    banned = long_lines("une ligne de sortie assez longue pour compter\nune autre ligne longue du banc à exclure\n")
    one = "Commande : x\nSortie :\nune ligne de sortie assez longue pour compter\nautre chose"
    two = one + "\nune autre ligne longue du banc à exclure"
    assert not contaminated(one, banned)
    assert contaminated(two, banned)


def test_header_lines_never_count_as_shared_output():
    header = "Statut : succès (code 0)\nDurée : 0.0 s ; 3 lignes affichées\nStatus: success (code 0)\n"
    assert long_lines(header) == set()


def test_speak_bench_lines_read_summary_outputs_and_qa_histories(tmp_path):
    lang = tmp_path / "fr"
    lang.mkdir()
    cases = [{"task": "summary", "output": "ligne de résumé suffisamment longue ici\n"},
             {"task": "qa", "history": [{"output": "ligne d'historique suffisamment longue ici\n"}]}]
    (lang / "dev.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cases))
    (lang / "test.jsonl").write_text("")
    lines = speak_bench_lines(tmp_path)
    assert "ligne de résumé suffisamment longue ici" in lines
    assert "ligne d'historique suffisamment longue ici" in lines


def _jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def test_cli_composes_every_source_with_its_production_prompt(tmp_path):
    fr_rec = raw(cmd="ls /srv", output="a.txt\nb.txt\n")
    fr_lost = raw(cmd="ls /opt", output="c.txt\n")
    en_rec = raw(cmd="ls /home", output="d.txt\ne.txt\n")
    en_rejected = raw(cmd="ls /var", output="f.txt\n")
    speak = raw(cmd="cat notes", output="première ligne du banc steph speak, longue\n"
                                        "deuxième ligne du banc steph speak, longue\n")
    mix = tmp_path / "mix"
    mix.mkdir()
    _jsonl(mix / "train.jsonl", [{"messages": labeled(fr_rec, "Succès. Fichiers a.txt et b.txt.")["messages"]},
                                 {"messages": labeled(fr_lost, "Succès. Fichier z.txt.")["messages"]},
                                 {"messages": labeled(speak, "Deux lignes.")["messages"]}])
    _jsonl(mix / "val.jsonl", [])
    _jsonl(tmp_path / "raw.jsonl", [fr_rec, fr_lost, speak])
    _jsonl(tmp_path / "en.jsonl", [labeled(en_rec, "Success. Files d.txt and e.txt.", "en", "macos.en"),
                                   labeled(en_rejected, "Success. File f.txt.", "en", "macos.en")])
    _jsonl(tmp_path / "en_raw.jsonl", [en_rec, en_rejected])
    rejected_sha = hashlib.sha256(build_messages(en_rejected, 1500, "en")[1]["content"].encode()).hexdigest()
    (tmp_path / "en_rejects.txt").write_text(rejected_sha + "\n")
    detail = {"source": "detail", "messages": [{"role": "system", "content": "détail court"},
                                               {"role": "user", "content": "Commande : df\nSortie :\n/dev/sda1 42G"},
                                               {"role": "assistant", "content": "sda1 42G."}]}
    # same user turn as a summary row, another task: neither a duplicate nor hit by the detail rejects
    detail_of_summary = {"source": "detail", "messages": [{"role": "system", "content": "détail court"},
                                                          labeled(fr_rec, "x")["messages"][1],
                                                          {"role": "assistant", "content": "a.txt, b.txt."}]}
    detail_rejected = {"source": "detail", "messages": [{"role": "system", "content": "détail court"},
                                                        {"role": "user", "content": "Commande : du\nSortie :\n4.0K x"},
                                                        {"role": "assistant", "content": "4.0K."}]}
    _jsonl(tmp_path / "detail.jsonl", [detail, detail_of_summary, detail_rejected])
    (tmp_path / "detail_rejects.txt").write_text(
        hashlib.sha256(detail_rejected["messages"][1]["content"].encode()).hexdigest() + "\n")
    bench = tmp_path / "speak" / "fr"
    bench.mkdir(parents=True)
    _jsonl(bench / "dev.jsonl", [{"task": "summary", "output": speak["output"]}])
    _jsonl(bench / "test.jsonl", [])

    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--fr-mix", str(mix), "--fr-raw", str(tmp_path / "raw.jsonl"),
         "--en", str(tmp_path / "en.jsonl"), "--en-raw", str(tmp_path / "en_raw.jsonl"),
         "--en-exclude", str(tmp_path / "en_rejects.txt"), "--feature", f"detail={tmp_path / 'detail.jsonl'}",
         "--feature-exclude", f"detail={tmp_path / 'detail_rejects.txt'}",
         "--speak-bench", str(tmp_path / "speak"), "--max-chars", "587", "--out", str(tmp_path / "k3")],
        capture_output=True, text=True, check=True).stdout
    counts = json.loads(out.strip().splitlines()[-1])

    rows = [json.loads(line) for name in ("train", "val") for line in (tmp_path / "k3" / f"{name}.jsonl").open()]
    by_source = {r["source"]: r["messages"] for r in rows if r["messages"][-1]["content"] != "a.txt, b.txt."}
    assert set(by_source) == {"fr_summary", "en_summary", "detail"}
    assert sum(r["source"] == "detail" for r in rows) == 2
    assert by_source["fr_summary"][0]["content"] == TRAIN_SYSTEM
    assert by_source["fr_summary"][2]["content"] == "Fichiers a.txt et b.txt."
    assert by_source["en_summary"][0]["content"] == TRAIN_SYSTEM_EN
    assert by_source["en_summary"][1] == build_messages(en_rec, 587, "en")[1]
    assert by_source["en_summary"][2]["content"] == "Files d.txt and e.txt."
    assert by_source["detail"] == detail["messages"]
    assert counts["fr_summary"]["lost_fact"] == 1
    assert counts["fr_summary"]["speak_bench"] == 1
    assert counts["en_summary"]["judge_reject"] == 1
    assert counts["detail"]["judge_reject"] == 1
    assert counts["kept_by_lang"] == {"fr": 3, "en": 1}


def test_cli_tags_english_questions_and_accepts_several_question_files(tmp_path):
    def qa(source, system, question, answer):
        return {"source": source, "messages": [{"role": "system", "content": system},
                                               {"role": "user", "content": "Historique :\n[1] ? $ true   (code 0, 0 s, 0 lignes)"},
                                               {"role": "assistant", "content": "ok"},
                                               {"role": "user", "content": question},
                                               {"role": "assistant", "content": answer}]}
    _jsonl(tmp_path / "qa_fr.jsonl", [qa("qa-synth", "fr", "Ça a marché ?", "Oui, code 0.")])
    _jsonl(tmp_path / "qa_en.jsonl", [qa("qa-synth.en", "en", "Did it work?", "Yes, code 0.")])
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--qa", str(tmp_path / "qa_fr.jsonl"), str(tmp_path / "qa_en.jsonl"),
         "--max-chars", "587", "--out", str(tmp_path / "mix")],
        capture_output=True, text=True, check=True).stdout
    counts = json.loads(out.strip().splitlines()[-1])
    rows = [json.loads(line) for name in ("train", "val") for line in (tmp_path / "mix" / f"{name}.jsonl").open()]
    assert sorted(r["source"] for r in rows) == ["qa", "qa_en"]
    assert counts["kept_by_lang"] == {"fr": 1, "en": 1}


def test_cli_counts_english_features_as_english(tmp_path):
    row = {"source": "start.en", "messages": [{"role": "system", "content": "en"},
                                              {"role": "user", "content": "ls -la"},
                                              {"role": "assistant", "content": "List files."}]}
    _jsonl(tmp_path / "start.en.jsonl", [row])
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--feature", f"start_en={tmp_path / 'start.en.jsonl'}",
         "--max-chars", "587", "--out", str(tmp_path / "mix")],
        capture_output=True, text=True, check=True).stdout
    assert json.loads(out.strip().splitlines()[-1])["kept_by_lang"] == {"en": 1}
