"""benchmark/run.py --system-prompt-file: score TermSpeak with a model's own training prompt
instead of the benchmark's system prompt, for a protocol comparison that must never be
folded into the standard leaderboard (steph's fine-tuned models learned a short French
system prompt, not TermSpeak's own longer one).
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmark"
DATA = BENCH / "data" / "v1"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = load("termspeak_run", BENCH / "run.py")
CONFIG = run.load_config(DATA)


def test_override_replaces_summary_system_for_every_language():
    overridden = run.override_summary_system(CONFIG["prompts"], "PROMPT D'ENTRAÎNEMENT COURT")
    assert overridden["fr"]["summary_system"] == "PROMPT D'ENTRAÎNEMENT COURT"
    assert overridden["en"]["summary_system"] == "PROMPT D'ENTRAÎNEMENT COURT"


def test_override_leaves_the_qa_system_and_other_keys_untouched():
    overridden = run.override_summary_system(CONFIG["prompts"], "X")
    assert overridden["fr"]["qa_system"] == CONFIG["prompts"]["fr"]["qa_system"]
    assert overridden["en"]["qa_system"] == CONFIG["prompts"]["en"]["qa_system"]
    assert overridden["input"] == CONFIG["prompts"]["input"]


def test_override_does_not_mutate_the_original_config():
    before = CONFIG["prompts"]["fr"]["summary_system"]
    run.override_summary_system(CONFIG["prompts"], "X")
    assert CONFIG["prompts"]["fr"]["summary_system"] == before


def reference_args(**overrides):
    """The subset of run.py's argparse namespace that run_lang() reads in --reference mode."""
    base = dict(data=str(DATA), split="test", limit=1, reference=True, label="", model="default",
                temperature=0.0, max_tokens=0, allow_thinking=False, no_warmup=False, extra_body="",
                system_prompt_file="", judge_model="", quiet=True)
    base.update(overrides)
    return argparse.Namespace(**base)


def test_default_run_has_no_system_prompt_override_in_the_result():
    result = run.run_lang(reference_args(), "fr", CONFIG)
    assert result["protocol"]["system_prompt_override"] is None
    assert result["protocol"]["system_prompt_file"] is None


def test_system_prompt_file_is_applied_and_recorded(tmp_path):
    prompt_file = tmp_path / "train_system.txt"
    prompt_file.write_text("Prompt d'entraînement de steph, très court.\n", encoding="utf-8")
    text = prompt_file.read_text(encoding="utf-8").strip()
    config = dict(CONFIG, prompts=run.override_summary_system(CONFIG["prompts"], text))

    result = run.run_lang(reference_args(system_prompt_file=str(prompt_file)), "fr", config)

    assert result["protocol"]["system_prompt_override"] == "Prompt d'entraînement de steph, très court."
    assert result["protocol"]["system_prompt_file"] == str(prompt_file)
    assert result["summary"]["score"] == 100.0  # references still score 100: only the prompt sent changes
