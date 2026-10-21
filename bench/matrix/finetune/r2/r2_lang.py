#!/usr/bin/env python3
"""R2 : réponses dans la mauvaise langue (classifieur lang_v3 de R3-T2), écart apparié par cas, A moins B.

    python3 r2_lang.py <harness.json> --a <runs A> --b <runs B>

Unité : l'évaluation (cas, langue du prompt) reaches_model ; valeur = part des graines où la réponse
est classée dans l'autre langue (réponses indéterminées comptées justes). Bootstrap apparié 10 000 tirages.

SPDX-License-Identifier: MIT
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "results/finetune/loop/round-3/r3t2p3"))
from lang_v3 import classify  # noqa: E402


def wrong_rates(harness, runs):
    out = defaultdict(list)
    for p in runs:
        for r in json.load(open(p))["rows"]:
            if harness[r["id"]]["reaches_model"]:
                got = classify(r.get("out") or "")
                out[r["id"]].append(1.0 if got is not None and got != r["id"].rsplit("@", 1)[1] else 0.0)
    return {k: float(np.mean(v)) for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("harness")
    ap.add_argument("--a", nargs="+", required=True)
    ap.add_argument("--b", nargs="+", required=True)
    a = ap.parse_args()
    harness = {c["id"]: c for c in json.load(open(a.harness))}
    wa, wb = wrong_rates(harness, a.a), wrong_rates(harness, a.b)
    res = {}
    for lang in ("all", "fr", "en"):
        ids = sorted(i for i in set(wa) & set(wb) if lang == "all" or i.endswith("@" + lang))
        d = np.array([wa[i] - wb[i] for i in ids])
        rng = np.random.default_rng(20260928)
        bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(10000)]
        res[lang] = {"n": len(ids), "wrong_a_pct": round(100 * np.mean([wa[i] for i in ids]), 2),
                     "wrong_b_pct": round(100 * np.mean([wb[i] for i in ids]), 2), "diff_pts": round(100 * d.mean(), 2),
                     "ci95": [round(100 * float(np.percentile(bs, 2.5)), 2), round(100 * float(np.percentile(bs, 97.5)), 2)]}
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
