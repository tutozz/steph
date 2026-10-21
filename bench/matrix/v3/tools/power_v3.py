#!/usr/bin/env python3
"""Statistical power of bench v3 (same method as T5, bench/matrix/loop/bench_power.py).

    python3 power_v3.py --split dev --a <A runs...> --b <B runs...> [--judge <verdicts.json>...] --out <power.json>

Paired by case: each model's score per evaluation (case x prompt language) is averaged over its
bench seeds, then over the two languages of a case, so the unit is the case (FR and EN answers
on one output are not independent). Paired bootstrap (10 000 draws, seed 20260928) on the mean
difference; MDE = (z0.975 + z0.80) x sd(case diff) / sqrt(n), for the dev, test and full sizes.
Inventions: judge A7 final verdict "invention" (douteux counted apart), same pairing.
Also reported: the seed-only noise (same model, bench seeds against each other), and the same
figures on the answers steph really sends to the model (reaches_model).

SPDX-License-Identifier: MIT
"""

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

import score_v3

Z = 1.959964 + 0.841621
B = 10_000


def boot_ci(d, rng):
    idx = rng.integers(0, len(d), size=(B, len(d)))
    bs = d[idx].mean(axis=1)
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def sign_test_p(pos, neg):
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def per_eval_quality(cases, runs):
    """{row id: [score per seed]}"""
    out = defaultdict(list)
    for p in runs:
        for rid, s in score_v3.score_file(cases, p)["per_case"].items():
            out[rid].append(s)
    return out


def per_eval_invention(verdicts, runs, kind="invention"):
    names = {Path(p).name for p in runs}
    out = defaultdict(list)
    for v in verdicts:
        if v["model_file"] in names and v["final"] != "erreur":
            out[v["id"]].append(1.0 if v["final"] == kind else 0.0)
    return out


def case_means(per_eval, keep=None):
    by_case = defaultdict(list)
    for rid, xs in per_eval.items():
        if keep is not None and rid not in keep:
            continue
        by_case[score_v3.parse_row_id(rid)[0]].append(float(np.mean(xs)))
    return {c: float(np.mean(v)) for c, v in by_case.items()}


def compare(a, b, sizes, rng, scale):
    common = sorted(set(a) & set(b))
    d = np.array([a[c] - b[c] for c in common])
    lo, hi = boot_ci(d, rng)
    sd = float(d.std(ddof=1))
    return {"n_cases": len(common), "a": round(scale * float(np.mean([a[c] for c in common])), 2),
            "b": round(scale * float(np.mean([b[c] for c in common])), 2),
            "diff": round(scale * float(d.mean()), 2), "ci95": [round(scale * lo, 2), round(scale * hi, 2)],
            "sd_case_diff": round(scale * sd, 2), "discordant_cases": int(np.sum(np.abs(d) > 1e-9)),
            "sign_test_p": round(sign_test_p(int(np.sum(d > 1e-9)), int(np.sum(d < -1e-9))), 4),
            "mde": {k: round(scale * Z * sd / math.sqrt(n), 2) for k, n in sizes.items()}}


def seed_noise(per_eval, sizes, scale):
    """Same model, two bench seeds against each other: MDE a pure resampling would reach."""
    seeds = min(len(v) for v in per_eval.values())
    sds = []
    for i in range(seeds):
        for j in range(i + 1, seeds):
            by_case = defaultdict(list)
            for rid, xs in per_eval.items():
                by_case[score_v3.parse_row_id(rid)[0]].append(xs[i] - xs[j])
            d = np.array([np.mean(v) for v in by_case.values()])
            sds.append(float(d.std(ddof=1)))
    sd = float(np.sqrt(np.mean(np.square(sds)))) if sds else float("nan")
    return {"sd_case_diff_one_seed": round(scale * sd, 2),
            "mde_three_seed_means": {k: round(scale * Z * sd / math.sqrt(3) / math.sqrt(n), 2) for k, n in sizes.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--a", nargs="+", required=True)
    ap.add_argument("--b", nargs="+", required=True)
    ap.add_argument("--judge", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rng = np.random.default_rng(20260928)
    cases = score_v3.load_cases(a.split)
    all_cases = score_v3.load_cases("all")
    harness = score_v3.load_harness(a.split)
    reach = {rid for rid, h in harness.items() if h["reaches_model"]}
    sizes = {"dev": sum(c["split"] == "dev" for c in all_cases.values()),
             "test": sum(c["split"] == "test" for c in all_cases.values()), "all": len(all_cases),
             "v2_equivalent_36": 36}
    qa, qb = per_eval_quality(cases, a.a), per_eval_quality(cases, a.b)
    # reaches_model subset: same share of cases in every split as measured on this split
    share = len({score_v3.parse_row_id(r)[0] for r in reach}) / len(cases)
    reach_sizes = {k: max(2, round(n * share)) for k, n in sizes.items()}
    report = {"method": __doc__.split("\n\n")[2].replace("\n", " "), "sizes_cases": sizes,
              "files_a": [Path(p).name for p in a.a], "files_b": [Path(p).name for p in a.b],
              "quality_pts": compare(case_means(qa), case_means(qb), sizes, rng, 100),
              "quality_pts_reaches_model": compare(case_means(qa, reach), case_means(qb, reach), reach_sizes, rng, 100),
              "quality_by_lang": {lang: compare(case_means(qa, {r for r in qa if r.endswith(lang)}),
                                                case_means(qb, {r for r in qb if r.endswith(lang)}), sizes, rng, 100)
                                  for lang in ("@fr", "@en")},
              "quality_seed_noise_a": seed_noise(qa, sizes, 100),
              "quality_seed_noise_b": seed_noise(qb, sizes, 100)}
    if a.judge:
        verdicts = [v for p in a.judge for v in json.load(open(p))]
        ia, ib = per_eval_invention(verdicts, a.a), per_eval_invention(verdicts, a.b)
        if ia and ib:
            report["inventions_pct_of_answers"] = compare(case_means(ia), case_means(ib), sizes, rng, 100)
            report["inventions_pct_reaches_model"] = compare(case_means(ia, reach), case_means(ib, reach), reach_sizes, rng, 100)
            report["inventions_seeds"] = {"a": min(len(v) for v in ia.values()), "b": min(len(v) for v in ib.values())}
            da, db = per_eval_invention(verdicts, a.a, "douteux"), per_eval_invention(verdicts, a.b, "douteux")
            report["douteux_pct_of_answers"] = {"a": round(100 * float(np.mean([np.mean(v) for v in da.values()])), 2),
                                                "b": round(100 * float(np.mean([np.mean(v) for v in db.values()])), 2)}
            if min(len(v) for v in ia.values()) > 1:
                report["inventions_seed_noise_a"] = seed_noise(ia, sizes, 100)
    Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
