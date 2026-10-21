#!/usr/bin/env python3
"""G5 : Steph Speak Bench, écart apparié par cas entre deux résultats de run.py (même langue, même split).

    python3 speak_pair.py <a.json> <b.json>

Bootstrap par cas, 10 000 tirages, graine 20260928 ; score en points (0-100), interdits en % de cas.

SPDX-License-Identifier: MIT
"""

import json
import sys

import numpy as np


def rows(p):
    return {r["id"]: r for r in json.load(open(p))["rows"]}


def main():
    a, b = rows(sys.argv[1]), rows(sys.argv[2])
    ids = sorted(set(a) & set(b))
    rng = np.random.default_rng(20260928)
    out = {"n": len(ids)}
    for k, f in (("score", lambda r: 100 * r["score"]), ("forbidden", lambda r: 100 * bool(r["forbidden_hit"]))):
        d = np.array([f(a[i]) - f(b[i]) for i in ids])
        bs = d[rng.integers(0, len(d), size=(10_000, len(d)))].mean(axis=1)
        out[k] = {"a": round(float(np.mean([f(a[i]) for i in ids])), 1), "b": round(float(np.mean([f(b[i]) for i in ids])), 1),
                  "diff": round(float(d.mean()), 2), "ci95": [round(float(np.percentile(bs, 2.5)), 2),
                                                             round(float(np.percentile(bs, 97.5)), 2)]}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
