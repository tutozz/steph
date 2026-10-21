#!/usr/bin/env python3
"""G5e : juge fort « juste et utile » (TEST de décision), écart apparié par évaluation entre G5e, a-sft et G5c (useful_pair.py de G5c).

    python3 useful_pair.py <verdicts.json> <runs/> <dev|test>   (runs/<modèle>-<split>-b7.json)

Évaluations gardées : celles que le juge a notées pour les trois modèles. Bootstrap 2 000 tirages, graine 20260928.

SPDX-License-Identifier: MIT
"""

import json
import random
import statistics as st
import sys

MODELS = ("g5e", "a-sft", "g5c")


def main():
    verdicts = {(v["id"], v["answer"]): v for v in json.load(open(sys.argv[1]))}
    runs = {m: {r["id"]: r.get("out") for r in json.load(open(f"{sys.argv[2]}/{m}-{sys.argv[3]}-b7.json"))["rows"]} for m in MODELS}

    def judged(m, i):
        out = runs[m].get(i)
        return out is not None and verdicts.get((i, out), {}).get("note") is not None

    ids = [i for i in runs["g5e"] if all(judged(m, i) for m in MODELS)]

    def val(m, i, k):
        v = verdicts[(i, runs[m][i])]
        return float(v["note"]) if k == "note" else 100.0 * bool(v["invention"])

    rng = random.Random(20260928)
    report = {"n": len(ids), "models": {}, "pairs": {}}
    for m in MODELS:
        report["models"][m] = {"useful": round(st.mean(val(m, i, "note") for i in ids), 1),
                               "inventions_pct": round(st.mean(val(m, i, "invention") for i in ids), 1),
                               "fr": round(st.mean(val(m, i, "note") for i in ids if i.endswith("@fr")), 1),
                               "en": round(st.mean(val(m, i, "note") for i in ids if i.endswith("@en")), 1)}
    for a, b in (("g5e", "a-sft"), ("g5e", "g5c"), ("g5c", "a-sft")):
        for k in ("note", "invention"):
            d = [val(a, i, k) - val(b, i, k) for i in ids]
            bs = sorted(st.mean(rng.choices(d, k=len(d))) for _ in range(2000))
            report["pairs"][f"{a} - {b} {k}"] = {"diff": round(st.mean(d), 2), "ci95": [round(bs[50], 2), round(bs[1949], 2)]}
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
