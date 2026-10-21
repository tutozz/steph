#!/usr/bin/env python3
"""D4 : tableau mode actuel contre mode à outils, depuis les sorties de p20_qa_latency.py.

    python3 bench/matrix/d4_summary.py --split dev <label>=<run-b7.json>,<run-b42.json>,<run-b123.json> [...]
        [--judge <verdicts.json>] [--pair <label A>:<label B>]

Par étiquette : qualité questions (score_v3, moyenne des graines), sous-groupes réponse présente et
réponse absente (`answer_in_history` du cas), appels d'outils par question, repli sur le mode actuel,
premier fait (question -> premier morceau envoyé à la fenêtre) médiane et p90, inventions au juge A7
si un fichier de verdicts de judge_v3.py est donné. `--pair` : écart B - A par cas (moyenne des graines
et des deux langues, comme power_v3.py), intervalle à 95 % par bootstrap apparié, 10 000 tirages.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "v3" / "tools"))
from score_v3 import load_cases, parse_row_id, score_answer  # noqa: E402


def pct(xs):
    return round(100 * sum(xs) / len(xs), 1) if xs else None


def p90(xs):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))], 2) if xs else None


def per_case(cases: dict, paths: list[str]) -> dict:
    scores: dict[str, list[float]] = {}
    for path in paths:
        for r in json.load(open(path))["rows"]:
            case_id, lang = parse_row_id(r["id"])
            scores.setdefault(case_id, []).append(score_answer(cases[case_id], lang, r.get("out") or ""))
    return {k: sum(v) / len(v) for k, v in scores.items()}


def paired(cases: dict, a: list[str], b: list[str], draws: int = 10000) -> dict:
    sa, sb = per_case(cases, a), per_case(cases, b)
    common = sorted(set(sa) & set(sb))
    diffs = [sb[k] - sa[k] for k in common]
    rng = random.Random(0)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(draws))
    return {"cases": len(common), "diff": round(100 * sum(diffs) / len(diffs), 1),
            "ci95": [round(100 * means[int(0.025 * draws)], 1), round(100 * means[int(0.975 * draws)], 1)]}


def summarize(cases: dict, paths: list[str], verdicts: dict | None = None) -> dict:
    per_seed, present, absent, calls, fallback, ttft, names = [], [], [], [], [], [], {}
    never_hits = 0
    for path in paths:
        rows = json.load(open(path))["rows"]
        seed_scores = []
        for r in rows:
            case_id, lang = parse_row_id(r["id"])
            case = cases[case_id]
            s = score_answer(case, lang, r.get("out") or "")
            seed_scores.append(s)
            (present if case["answer_in_history"] else absent).append(s)
            if r.get("ttft") is not None:
                ttft.append(r["ttft"])
            tools = r.get("tools")
            if tools:
                fallback.append(bool(tools.get("fallback")))
                calls.append(len(tools.get("names") or []))
                for n in tools.get("names") or []:
                    names[n] = names.get(n, 0) + 1
            if s == 0 and r.get("out"):
                never_hits += 1
        per_seed.append(pct(seed_scores))
    out = {
        "quality": round(statistics.mean(per_seed), 1),
        "per_seed": per_seed,
        "present": pct(present), "absent": pct(absent),
        "n_present": len(present), "n_absent": len(absent),
        "calls_mean": round(statistics.mean(calls), 2) if calls else None,
        "fallback_pct": pct(fallback) if fallback else None,
        "tool_names": names,
        "ttft_median": round(statistics.median(ttft), 2) if ttft else None,
        "ttft_p90": p90(ttft),
        "zero_score_answers": never_hits,
    }
    if verdicts:
        files = {Path(p).name for p in paths}
        v = [x["final"] for x in verdicts if x["model_file"] in files and x["final"] in ("ok", "invention", "douteux")]
        out["inventions_pct"] = pct([x == "invention" for x in v])
        out["doubtful_pct"] = pct([x == "douteux" for x in v])
        out["judged"] = len(v)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--judge", action="append", default=[])
    ap.add_argument("--pair", action="append", default=[])
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    cases = load_cases(a.split)
    verdicts = [v for path in a.judge for v in json.load(open(path))]
    table, files = {}, {}
    for spec in a.runs:
        label, paths = spec.split("=", 1)
        files[label] = paths.split(",")
        table[label] = summarize(cases, files[label], verdicts)
    for spec in a.pair:
        la, lb = spec.split(":")
        table[f"{lb} - {la}"] = paired(cases, files[la], files[lb])
    print(json.dumps(table, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
