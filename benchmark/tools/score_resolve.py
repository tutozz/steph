#!/usr/bin/env python3
"""Score steph's resolve() shortcut (src/steph/digest.py) on Steph Speak Bench, no model, no server.

resolve() is deterministic and French-only: it turns a finished command (cmd, exit code,
output) straight into a spoken sentence for the cases it recognizes (compile errors,
tracebacks, pytest, apt/pip, git, network, disk and hardware messages), with no LLM call.
It has no access to a conversation history, so "qa" cases are out of its scope and
excluded here, not scored as a failure.

This reuses run.py's scoring and summary so a resolve() result is written and read exactly
like a model's, but it is its own labeled row in results/ and the leaderboard - never
averaged into a model's score, never shown in the same column without its label.

    python3 benchmark/tools/score_resolve.py --lang all --split test

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
ROOT = BENCH.parent
DEFAULT_DATA = BENCH / "data" / "v1"
DEFAULT_OUT = BENCH / "results"

MODEL_LABEL = "steph-resolve"


def _load_run():
    spec = importlib.util.spec_from_file_location("termspeak_run", BENCH / "run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("termspeak_run", module)
    spec.loader.exec_module(module)
    return module


run = _load_run()
sys.path.insert(0, str(ROOT / "src"))
from steph.digest import resolve  # noqa: E402  (steph itself, not a benchmark dependency)


def score_resolve(cases: list, scoring: dict) -> list:
    """One scored row per "summary" case. "qa" cases are skipped: resolve() takes no history."""
    rows = []
    for case in cases:
        if case["task"] != "summary":
            continue
        answer = resolve(case["cmd"], case["exit"], case["output"]) or ""
        row = {"id": case["id"], "category": case["category"], "task": case["task"],
               "answer": answer or None}
        row.update(run.score_case(case, answer, scoring))
        rows.append(row)
    return rows


def run_lang(lang: str, split: str, data_dir: Path, config: dict) -> dict:
    cases = run.load_cases(data_dir, lang, split)
    rows = score_resolve(cases, config["scoring"])
    skipped = len(cases) - len(rows)
    return {
        "benchmark": run.BENCHMARK, "data_version": data_dir.name, "lang": lang, "split": split,
        "data_sha256": {f"{lang}/{p.name}": run.sha256(p) for p in run.case_files(data_dir, lang, split)},
        "config_sha256": {"prompts": run.sha256(data_dir / "prompts.json"),
                          "scoring": run.sha256(data_dir / "scoring.json")},
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": {"label": MODEL_LABEL, "name": "steph.digest.resolve"},
        "protocol": {"mode": "resolve", "decoding": None, "note": "règles Python déterministes, aucun LLM"},
        "backend": {"name": "steph.digest", "version": None},
        "hardware": None,
        "hardware_note": "sans objet : aucun modèle, temps de réponse non pertinent",
        "notes": (f"resolve() seul (src/steph/digest.py), toujours en français, sans repli sur un modèle ; "
                  f"cas qa hors périmètre car resolve() n'a pas l'historique "
                  f"({skipped} sur {len(cases)} exclus) ; jamais à comparer à une colonne de score d'un "
                  f"modèle sans lire ce champ notes" +
                  (" ; ATTENTION split test : si resolve() a été étendu en lisant des cas de ce split, "
                   "ce score est contaminé et optimiste, à ne publier que marqué comme tel"
                   if split == "test" else "")),
        "rows": rows,
        "summary": run.summarize(rows),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Score steph's resolve() shortcut on Steph Speak Bench (no model).")
    ap.add_argument("--lang", default="en", choices=["en", "fr", "all"])
    ap.add_argument("--split", default="test", choices=["dev", "test", "all"])
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args(argv)
    config = run.load_config(Path(a.data))
    for lang in (["en", "fr"] if a.lang == "all" else [a.lang]):
        result = run_lang(lang, a.split, Path(a.data), config)
        run.print_table(result)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = Path(a.out) / f"{stamp}_{run.slug(MODEL_LABEL)}_{lang}_{a.split}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
