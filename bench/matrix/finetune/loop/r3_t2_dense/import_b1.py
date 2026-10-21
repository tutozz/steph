#!/usr/bin/env python3
"""R3-T2 partie 2 : reprend les verdicts A7 déjà rendus par b1_judge.py (R3-B1, partie 3) dans le cache de
judge_bench_fast.py, pour ne jamais rejuger une réponse identique au même cas.

    python3 import_b1.py --harness dev.json --out cache/bench-seed.jsonl --verdicts v1.jsonl [...] -- runs/*.json

Clé b1 : sha256(contexte + NUL + réponse)[:20] ; clé du cache : sha256(id + NUL + réponse). Même juge (A7 intact),
mêmes deux passes, même verdict final ; seuls les verdicts sans erreur sont repris.

SPDX-License-Identifier: MIT
"""

import argparse
import hashlib
import json

from mask_pairs import cache_key, judge_context


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--verdicts", nargs="+", required=True)
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    harness = {c["id"]: c for c in json.load(open(a.harness))}
    b1 = {}
    for p in a.verdicts:
        for line in open(p, encoding="utf-8"):
            if line.strip():
                v = json.loads(line)
                if v["final"] != "erreur":
                    b1[v["key"]] = v
    seeded, seen = 0, set()
    with open(a.out, "w", encoding="utf-8") as f:
        for p in a.runs:
            for r in json.load(open(p))["rows"]:
                h, text = harness[r["id"]], r.get("out")
                if not h["reaches_model"] or not text or not text.strip():
                    continue
                k = cache_key(r["id"], text)
                ctx = judge_context(h["messages"])
                v = b1.get(hashlib.sha256((ctx + "\x00" + text).encode()).hexdigest()[:20])
                if v is None or k in seen:
                    continue
                seen.add(k)
                f.write(json.dumps({"key": k, "id": r["id"], "phrase": text, "pass_A": v["pass_A"],
                                    "pass_B": v["pass_B"], "final": v["final"]}, ensure_ascii=False) + "\n")
                seeded += 1
    print(json.dumps({"b1_verdicts": len(b1), "seeded": seeded}))


if __name__ == "__main__":
    main()
