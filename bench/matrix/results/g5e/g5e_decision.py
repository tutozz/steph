#!/usr/bin/env python3
"""G5e (g5c_decision.py de G5c) : inventions au TEST, juge A7 et juge fort au même poids (règle de décision du 2026-10-01).

    PYTHONPATH=<v3/tools> python3 g5e_decision.py <runs/> <vall/> <useful/verdicts-test.json> <out.json>

Par évaluation jugée des deux côtés : taux A7 (moyenne des 3 graines, verdicts hors erreur), indicateur du juge fort
(graine 7) ; score combiné = moitié de chacun. Écarts appariés par cas (power_v3.compare, bootstrap 10 000 tirages,
graine 20260928) pour G5e - a-sft, G5e - G5c et G5c - a-sft, sur chaque juge seul et combiné.

SPDX-License-Identifier: MIT
"""

import json
import sys
from pathlib import Path

import numpy as np

import power_v3

SEEDS = (7, 42, 123)
MODELS = ("g5e", "a-sft", "g5c")


def main():
    rd, vd, uv, outp = sys.argv[1:5]
    verd = []
    for m in MODELS:
        for s in SEEDS:
            verd += json.load(open(Path(vd) / f"inv-{m}-test-b{s}.json"))
    strong = {(v["id"], v["answer"]): v for v in json.load(open(uv)) if v["note"] is not None}
    a7, fort = {}, {}
    for m in MODELS:
        files = [str(Path(rd) / f"{m}-test-b{s}.json") for s in SEEDS]
        a7[m] = {i: float(np.mean(x)) for i, x in power_v3.per_eval_invention(verd, files).items()}
        rows = {r["id"]: r.get("out") for r in json.load(open(Path(rd) / f"{m}-test-b7.json"))["rows"]}
        fort[m] = {i: 1.0 if strong[(i, o)]["invention"] else 0.0 for i, o in rows.items() if (i, o) in strong}
    ids = set.intersection(*(set(a7[m]) & set(fort[m]) for m in MODELS))
    both = {m: {i: 0.5 * a7[m][i] + 0.5 * fort[m][i] for i in ids} for m in MODELS}
    rng = np.random.default_rng(20260928)
    rep = {"n_evals": len(ids), "models": {}, "pairs": {}}
    for m in MODELS:
        rep["models"][m] = {k: round(100 * float(np.mean([d[m][i] for i in ids])), 1)
                            for k, d in (("a7", a7), ("fort", fort), ("combined", both))}
    for a, b in (("g5e", "a-sft"), ("g5e", "g5c"), ("g5c", "a-sft")):
        rep["pairs"][f"{a} - {b}"] = {
            k: {x: c[x] for x in ("n_cases", "diff", "ci95", "sign_test_p")}
            for k, d in (("a7", a7), ("fort", fort), ("combined", both))
            for c in [power_v3.compare(power_v3.case_means({i: [d[a][i]] for i in ids}),
                                       power_v3.case_means({i: [d[b][i]] for i in ids}), {"test": 654}, rng, 100)]}
    Path(outp).write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
