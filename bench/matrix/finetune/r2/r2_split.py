#!/usr/bin/env python3
"""R2 : écart apparié de qualité v3 par tâche (résumé, question) et par langue du prompt, même méthode que power_v3.

    python3 r2_split.py --split test --a <runs A> --b <runs B>

SPDX-License-Identifier: MIT
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "v3" / "tools"))
import power_v3  # noqa: E402
import score_v3  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--a", nargs="+", required=True)
    ap.add_argument("--b", nargs="+", required=True)
    a = ap.parse_args()
    cases = score_v3.load_cases(a.split)
    qa = power_v3.per_eval_quality(cases, a.a)
    qb = power_v3.per_eval_quality(cases, a.b)
    out = {}
    for task in ("summary", "qa"):
        for lang in ("all", "fr", "en"):
            keep = {r for r in qa if cases[score_v3.parse_row_id(r)[0]]["task"] == task
                    and (lang == "all" or r.endswith("@" + lang))}
            ma, mb = power_v3.case_means(qa, keep), power_v3.case_means(qb, keep)
            res = power_v3.compare(ma, mb, {"test": len(ma)}, np.random.default_rng(20260928), 100)
            out[f"{task}/{lang}"] = {k: res[k] for k in ("n_cases", "a", "b", "diff", "ci95")}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
