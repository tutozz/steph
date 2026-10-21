import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench/matrix/finetune"))

from label import build_messages  # noqa: E402
from build_dataset_release import (  # noqa: E402
    CANARY,
    build_sft,
    compose,
    contains_canary,
    documented_pair,
    documented_row,
    header_key,
    index_raw,
    is_neutral_source,
    language_for_source,
    loses_fact,
    match_raw,
    provenance_for_task,
    rebuild_summary_row,
    split_for,
    strip_status,
    task_for_source,
)

SCRIPT = ROOT / "bench/matrix/finetune/build_dataset_release.py"


def raw(cmd="ls /srv", exit_code=0, duration=0.2, output="a.txt\nb.txt\nc.txt\n"):
    return {"cmd": cmd, "exit": exit_code, "duration": duration, "output": output}


def row(source, user, label, extra_system="s"):
    return {"messages": [{"role": "system", "content": extra_system},
                         {"role": "user", "content": user},
                         {"role": "assistant", "content": label}], "source": source}


# --------------------------------------------------------------------- taxonomy

def test_task_for_source_recognizes_feature_and_qa_sources():
    assert task_for_source("detail") == "detail"
    assert task_for_source("start") == "start"
    assert task_for_source("progress") == "progress"
    assert task_for_source("flux") == "flux"
    assert task_for_source("summary_residual") == "summary_residual"
    assert task_for_source("qa-synth") == "qa"


def test_task_for_source_defaults_unknown_sources_to_summary():
    assert task_for_source("linux-dev") == "summary"
    assert task_for_source("macos.en") == "summary"
    assert task_for_source("snapshot-linux-low") == "summary"


def test_language_for_source_reads_the_en_suffix():
    assert language_for_source("macos") == "fr"
    assert language_for_source("macos.en") == "en"
    assert language_for_source("linux-low.en") == "en"


def test_provenance_for_task_marks_qa_as_synthetic():
    assert provenance_for_task("qa") == "synthetic_session"
    assert provenance_for_task("summary") == "real_capture"
    assert provenance_for_task("detail") == "real_capture"


def test_is_neutral_source_accepts_known_shapes():
    for s in ("linux-dev", "macos.en", "snapshot-linux-low", "detail", "qa-synth"):
        assert is_neutral_source(s)


def test_is_neutral_source_rejects_paths_and_hostnames():
    assert not is_neutral_source("/home/alice")
    assert not is_neutral_source("dev@lab")
    assert not is_neutral_source("Machine-1")
    assert not is_neutral_source("")


# --------------------------------------------------------------------- status / header

def test_strip_status_handles_french_and_english():
    assert strip_status("Échec. main.rs ligne 3 : type attendu.", "fr") == "main.rs ligne 3 : type attendu."
    assert strip_status("Succès. Fichier créé.", "fr") == "Fichier créé."
    assert strip_status("Failed. main.rs line 3: expected type.", "en") == "main.rs line 3: expected type."
    assert strip_status("Copie réussie.", "fr") == "Copie réussie."


def test_header_key_splits_on_the_language_marker():
    fr = "Commande : ls\nStatut : succès (code 0)\nSortie :\na.txt"
    en = "Command: ls\nStatus: success (code 0)\nOutput:\na.txt"
    assert header_key(fr, "fr") == "Commande : ls\nStatut : succès (code 0)\n"
    assert header_key(en, "en") == "Command: ls\nStatus: success (code 0)\n"


# --------------------------------------------------------------------- raw matching

def test_match_raw_finds_the_only_candidate():
    rec = raw()
    user = build_messages(rec, 1500, "fr")[1]["content"]
    index = index_raw([rec], "fr")
    assert match_raw(user, index, "fr") is rec


def test_match_raw_breaks_ties_on_output_then_gives_up():
    first, second = raw(output="x.txt\n"), raw(output="y.txt\n")
    index = index_raw([first, second], "fr")
    user = build_messages(second, 1500, "fr")[1]["content"]
    assert match_raw(user, index, "fr") is second


def test_match_raw_works_in_english():
    rec = raw(cmd="ls /srv", output="a.txt\nb.txt\n")
    user = build_messages(rec, 1500, "en")[1]["content"]
    index = index_raw([rec], "en")
    assert match_raw(user, index, "en") is rec


def test_match_raw_returns_none_for_an_unknown_header():
    assert match_raw("Commande : uptime\nStatut : succès (code 0)\nSortie :\nup", {}, "fr") is None


# --------------------------------------------------------------------- grounding

def test_loses_fact_flags_a_label_that_cites_an_absent_file():
    user = "Commande : ls\nStatut : succès (code 0)\nSortie :\na.txt\nb.txt"
    assert loses_fact(user, "Trois fichiers, dont c.txt.")
    assert not loses_fact(user, "Fichiers a.txt et b.txt.")


# --------------------------------------------------------------------- rebuild

def test_rebuild_summary_row_uses_the_short_system_prompt_for_the_row_language():
    rec = raw(cmd="journalctl -n 200", exit_code=1, output="".join(f"line {i}\n" for i in range(200)))
    old = row("linux-dev", build_messages(rec, 1500, "fr")[1]["content"], "Échec. Journal de 200 lignes.")
    new = rebuild_summary_row(old, rec, 300, "fr")
    assert new["messages"][0]["content"].startswith("Tu lis la sortie d'une commande de terminal")
    assert new["messages"][2]["content"] == "Journal de 200 lignes."
    assert len(new["messages"][1]["content"]) <= len(build_messages(rec, 1500, "fr")[1]["content"])


def test_rebuild_summary_row_in_english_uses_the_english_short_prompt():
    rec = raw(cmd="ls", output="a.txt\n")
    old = row("macos.en", build_messages(rec, 1500, "en")[1]["content"], "Failed, code 1. a.txt.")
    new = rebuild_summary_row(old, rec, 300, "en")
    assert new["messages"][0]["content"].startswith("You read the output of a terminal command")
    assert new["messages"][2]["content"] == "a.txt."


# --------------------------------------------------------------------- composition

def test_compose_drops_duplicates_and_judge_rejects():
    kept_row = row("linux-dev", "Commande : ls\nSortie :\na.txt", "a.txt.")
    dup_row = row("linux-dev", "Commande : ls\nSortie :\na.txt", "a.txt.")
    rejected_row = row("macos", "Commande : df\nSortie :\ndisk", "libre.")
    rejected_hash = hashlib.sha256(rejected_row["messages"][1]["content"].encode()).hexdigest()

    kept, stats = compose([kept_row, dup_row, rejected_row], {rejected_hash}, cap=120)

    assert kept == [kept_row]
    assert stats["duplicate"] == 1
    assert stats["judge_reject"] == 1


def test_compose_caps_snapshot_rows_per_program_but_not_the_rest():
    rows = [row("snapshot-linux-dev", f"Commande : gcc f{i}.c\nSortie :\nok{i}", f"ok {i}.") for i in range(3)]
    kept, stats = compose(rows, set(), cap=2)
    assert len(kept) == 2
    assert stats["program_cap"] == 1


def test_compose_never_caps_the_main_corpus():
    rows = [row("linux-dev", f"Commande : gcc f{i}.c\nSortie :\nok{i}", f"ok {i}.") for i in range(5)]
    kept, stats = compose(rows, set(), cap=2)
    assert len(kept) == 5
    assert stats["program_cap"] == 0


# --------------------------------------------------------------------- build_sft grounding scope

def test_build_sft_does_not_ground_check_feature_rows(tmp_path):
    # "start" sends the bare command as input (no output to ground a cause against);
    # the label below infers what the tool does, which a literal grounding check would
    # reject even though the H3a judge already approved this kind of row.
    detail_row = row("start", "gcc -Wall -o prog prog.c", "Compile prog.c avec GCC, avertissements actifs.")
    splits, stats = build_sft([detail_row], tmp_path, max_chars=300)
    kept = splits["train"] + splits["validation"]
    assert len(kept) == 1
    assert stats["start_kept"] == 1
    assert "start_lost_fact" not in stats


def test_build_sft_still_ground_checks_summary_rows_without_a_raw_match(tmp_path):
    ungrounded = row("linux-dev", "Commande : ls\nStatut : succès (code 0)\nSortie :\na.txt",
                     "Trois fichiers, dont c.txt.")
    splits, stats = build_sft([ungrounded], tmp_path, max_chars=300)
    kept = splits["train"] + splits["validation"]
    assert kept == []
    assert stats["summary_lost_fact_no_raw"] == 1


# --------------------------------------------------------------------- split / documentation

def test_split_for_is_deterministic_and_mixes_train_and_validation():
    texts = [f"Commande : cmd{i}\nSortie :\nx" for i in range(200)]
    splits = {split_for(t) for t in texts}
    assert splits == {"train", "validation"}
    assert split_for(texts[0]) == split_for(texts[0])


def test_documented_row_carries_the_release_metadata():
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
               {"role": "assistant", "content": "a"}]
    d = documented_row(messages, "macos.en", resynced=True)
    assert d == {
        "messages": messages, "language": "en", "task": "summary", "source": "macos.en",
        "provenance": "real_capture", "labeler": "qwen3.5-9b", "judge": "qwen3.5-9b-2pass",
        "resynced": True,
    }


def test_documented_pair_detects_language_from_the_prompt():
    fr_pair = {"prompt": [{"role": "system", "content": "s"}, {"role": "user", "content": "Commande : ls"}],
              "chosen": "a.txt.", "rejected": "b.txt."}
    en_pair = {"prompt": [{"role": "system", "content": "s"}, {"role": "user", "content": "Command: ls"}],
              "chosen": "a.txt.", "rejected": "b.txt."}
    assert documented_pair(fr_pair)["language"] == "fr"
    assert documented_pair(en_pair)["language"] == "en"
    assert documented_pair(fr_pair)["task"] == "summary"
    assert documented_pair(fr_pair)["source"] == "preference-pairs"


# --------------------------------------------------------------------- contamination

def test_contains_canary_detects_the_benchmark_canary():
    assert contains_canary(f"une ligne avec {CANARY} dedans")
    assert not contains_canary("une ligne normale")


# --------------------------------------------------------------------- CLI end to end

def test_cli_builds_sft_configuration_from_final_and_raw(tmp_path):
    final_dir = tmp_path / "final"
    final_dir.mkdir()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    rec = raw(cmd="ls /srv", output="a.txt\nb.txt\n")
    (raw_dir / "linux-dev.jsonl").write_text(json.dumps(rec) + "\n")

    kept_row = row("linux-dev", build_messages(rec, 1500, "fr")[1]["content"], "Succès. a.txt et b.txt.")
    detail_row = row("detail", "Commande : ls\nSortie :\na.txt\nb.txt", "a.txt puis b.txt.")
    (final_dir / "train.jsonl").write_text(json.dumps(kept_row) + "\n" + json.dumps(detail_row) + "\n")

    qa_row = {"source": "qa-synth", "messages": [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "Historique :\n[1] ? $ ls\na.txt"},
        {"role": "assistant", "content": "Compris."},
        {"role": "user", "content": "Quel fichier ?"},
        {"role": "assistant", "content": "a.txt."}]}
    (final_dir / "qa_train.jsonl").write_text(json.dumps(qa_row) + "\n")

    exclude = tmp_path / "judge-rejects.txt"
    exclude.write_text("")
    out_dir = tmp_path / "release"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--final", str(final_dir), "--raw-dir", str(raw_dir),
         "--exclude", str(exclude), "--max-chars", "300", "--out", str(out_dir)],
        capture_output=True, text=True, check=True)

    manifest = json.loads(result.stdout.strip().splitlines()[-1])
    assert manifest["sft"]["train"] + manifest["sft"]["validation"] == 3

    rows = [json.loads(line) for name in ("train", "validation")
            for line in (out_dir / "sft" / f"{name}.jsonl").open()]
    assert {r["task"] for r in rows} == {"summary", "detail", "qa"}
    assert all(set(r) == {"messages", "language", "task", "source", "provenance",
                          "labeler", "judge", "resynced"} for r in rows)


def test_cli_writes_empty_dpo_configuration_when_no_pairs_are_given(tmp_path):
    final_dir = tmp_path / "final"
    final_dir.mkdir()
    (final_dir / "train.jsonl").write_text("")
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    exclude = tmp_path / "judge-rejects.txt"
    exclude.write_text("")
    out_dir = tmp_path / "release"

    subprocess.run(
        [sys.executable, str(SCRIPT), "--final", str(final_dir), "--raw-dir", str(raw_dir),
         "--exclude", str(exclude), "--max-chars", "300", "--out", str(out_dir)],
        capture_output=True, text=True, check=True)

    assert (out_dir / "dpo" / "train.jsonl").read_text() == ""
    assert (out_dir / "dpo" / "validation.jsonl").read_text() == ""


def test_cli_aborts_without_writing_when_the_canary_leaked_in(tmp_path):
    final_dir = tmp_path / "final"
    final_dir.mkdir()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    tainted = row("detail", f"Commande : ls\nSortie :\n{CANARY}", "présent.")
    (final_dir / "train.jsonl").write_text(json.dumps(tainted) + "\n")
    exclude = tmp_path / "judge-rejects.txt"
    exclude.write_text("")
    out_dir = tmp_path / "release"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--final", str(final_dir), "--raw-dir", str(raw_dir),
         "--exclude", str(exclude), "--max-chars", "300", "--out", str(out_dir)],
        capture_output=True, text=True)

    assert result.returncode != 0
    assert not out_dir.exists()
