"""r3t5_compare.py <harness.json> <tok_orig.json> <tok_trim.json> <map.json> <runA.json> <runB.json> [<runA2.json>]

Share of identical answers between two bench runs, split by whether the prompt tokenizes
identically after trimming (tok_* from r3t5_tokenize.py on the same harness order).
runA2, a repeat of runA, gives the floor of run-to-run noise.

SPDX-License-Identifier: MIT
"""
import json
import sys

harness = json.load(open(sys.argv[1]))
tok_a, tok_b = json.load(open(sys.argv[2])), json.load(open(sys.argv[3]))
old = json.load(open(sys.argv[4]))["old_ids"]
same_tok = {c["id"]: [old[t] for t in b] == a for c, a, b in zip(harness, tok_a, tok_b)}
reach = {c["id"]: bool(c.get("reaches_model")) for c in harness}


def outs(p):
    return {r["id"]: r.get("out") for r in json.load(open(p))["rows"]}


A, B = outs(sys.argv[5]), outs(sys.argv[6])
res = {}


def rate(x, y, ids):
    ids = [i for i in ids if i in x and i in y]
    return {"n": len(ids), "identical": sum(x[i] == y[i] for i in ids),
            "pct": round(100 * sum(x[i] == y[i] for i in ids) / max(len(ids), 1), 2)}


groups = {"all": list(same_tok), "same_tokens": [i for i, s in same_tok.items() if s],
          "diff_tokens": [i for i, s in same_tok.items() if not s],
          "reaches_model": [i for i in same_tok if reach[i]],
          "fr": [i for i in same_tok if i.endswith("@fr")], "en": [i for i in same_tok if i.endswith("@en")]}
res["trim_vs_ref"] = {g: rate(A, B, ids) for g, ids in groups.items()}
if len(sys.argv) > 7:
    A2 = outs(sys.argv[7])
    res["ref_repeat"] = {g: rate(A, A2, ids) for g, ids in groups.items()}
print(json.dumps(res, indent=1))
