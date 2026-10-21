#!/usr/bin/env python3
"""P20 : p50 / p90 / max du premier jeton et du premier son de runs p20_qa_latency.py.

    python3 p20_summary.py run1.json [run2.json ...]

Deux populations : les 90 évaluations questions du split dev v3, et les 17 questions du
sous-ensemble dev60 de R2-B1 (select_dev60.py, graine 2, dev.json de 6eb7917).

SPDX-License-Identifier: MIT
"""

import json
import sys

DEV60_QA = set("""v3-history-qa-0030@fr v3-history-qa-0024@fr v3-history-qa-0105@fr v3-history-qa-0101@fr
v3-history-qa-0055@fr v3-history-qa-0056@fr v3-history-qa-0054@fr v3-history-qa-0088@en v3-history-qa-0049@en
v3-history-qa-0041@en v3-history-qa-0100@en v3-history-qa-0110@en v3-history-qa-0105@en v3-history-qa-0019@en
v3-history-qa-0053@en v3-history-qa-0087@en v3-history-qa-0052@en""".split())


def pct(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    f = int(k)
    return xs[f] + (xs[min(f + 1, len(xs) - 1)] - xs[f]) * (k - f)


def stats(rows, key):
    xs = [r[key] for r in rows if r.get(key) is not None]
    if not xs:
        return None
    return {"n": len(xs), "p50": round(pct(xs, 50), 2), "p90": round(pct(xs, 90), 2), "max": round(max(xs), 2)}


def summarize(path):
    d = json.load(open(path))
    rows = d["rows"]
    sub = [r for r in rows if r["id"] in DEV60_QA]
    return {"file": path.rsplit("/", 1)[-1], "regime": d["regime"], "delay": d.get("delay"),
            "dev90": {"ttft": stats(rows, "ttft"), "first_speech": stats(rows, "first_speech")},
            "dev60_qa17": {"ttft": stats(sub, "ttft"), "first_speech": stats(sub, "first_speech")}}


if __name__ == "__main__":
    print(json.dumps([summarize(p) for p in sys.argv[1:]], ensure_ascii=False, indent=1))
