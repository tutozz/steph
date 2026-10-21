#!/usr/bin/env python3
"""R2-C1 control: the A7 judge (2 passes) on a sample of injected rejected answers, and on their
chosen labels. Every rejected answer should be judged "invention"; the labels should stay "ok".

    PYTHONPATH=<A7 judge_lib dir> python3 judge_injected.py --pairs pairs-train.jsonl --n 50 --out control.json

Writes verdicts per pair (corpus text: stays on the corpus host) and prints counts only.

SPDX-License-Identifier: MIT
"""

import argparse
import collections
import json
import random
from concurrent.futures import ThreadPoolExecutor

from inject_pairs import context_of
from judge_lib import call_judge


def both(ctx, phrase):
    v = []
    for pid in ("A", "B"):
        r = {"verdict": "erreur"}
        for _ in range(3):
            try:
                r = call_judge(ctx, phrase, pass_id=pid, timeout=300)
            except Exception as e:
                r = {"verdict": "erreur", "_error": str(e)[:200]}
            if r["verdict"] in ("ok", "invention"):
                break
        v.append(r["verdict"])
    return "invention" if v == ["invention"] * 2 else "ok" if v == ["ok"] * 2 else "douteux" if "invention" in v else "erreur"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    pairs = [json.loads(l) for l in open(a.pairs, encoding="utf-8")]
    pairs = [p for p in pairs if "op" in p]
    rng = random.Random(a.seed)
    by_op = collections.defaultdict(list)
    for p in pairs:
        by_op[p["op"]].append(p)
    sample = []
    while len(sample) < min(a.n, len(pairs)):
        for op in sorted(by_op):
            if by_op[op] and len(sample) < a.n:
                sample.append(by_op[op].pop(rng.randrange(len(by_op[op]))))
    tasks = [(context_of(p["prompt"] + [{"role": "assistant", "content": ""}]), p) for p in sample]
    with ThreadPoolExecutor(a.threads) as ex:
        rej = list(ex.map(lambda t: both(t[0], t[1]["rejected"]), tasks))
        cho = list(ex.map(lambda t: both(t[0], t[1]["chosen"]), tasks))
    rows = [{"op": p["op"], "lang": p["lang"], "rejected": r, "chosen": c} for (_, p), r, c in zip(tasks, rej, cho)]
    json.dump(rows, open(a.out, "w"), ensure_ascii=False, indent=1)
    summary = {"n": len(rows), "rejected": dict(collections.Counter(r["rejected"] for r in rows)),
               "chosen": dict(collections.Counter(r["chosen"] for r in rows)),
               "rejected_by_op": {op: dict(collections.Counter(r["rejected"] for r in rows if r["op"] == op))
                                  for op in sorted({r["op"] for r in rows})}}
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
