#!/usr/bin/env python3
"""Construit les paires de préférences (P16) : chosen = étiquette ancrée du corpus,
rejected = sortie du modèle que les 2 passes du juge déclarent inventée.

    python3 build_pairs.py --data <dossier> --gen gen.jsonl --verdicts verdicts.jsonl --out <dossier>

Écrit pairs-train.jsonl et pairs-val.jsonl (contiennent du corpus : restent sur la machine) et
pairs-counts.json (comptes seuls, publiable).

SPDX-License-Identifier: MIT
"""

import argparse
import collections
import json
import os

from judge_outputs import key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--gen", required=True)
    ap.add_argument("--verdicts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-per-prompt", type=int, default=3)
    a = ap.parse_args()

    rows = {s: [json.loads(l)["messages"] for l in open(os.path.join(a.data, f"{s}.jsonl"))] for s in ("train", "val")}
    verdicts = {}
    for line in open(a.verdicts):
        v = json.loads(line)
        verdicts[v["key"]] = v["final"]
    finals = collections.Counter(verdicts.values())
    pairs = {"train": collections.defaultdict(list), "val": collections.defaultdict(list)}
    for line in open(a.gen):
        g = json.loads(line)
        msgs = rows[g["split"]][g["idx"]]
        if verdicts.get(key(msgs[1]["content"], g["out"])) != "invention":
            continue
        bucket = pairs[g["split"]][g["idx"]]
        if g["out"] not in bucket and len(bucket) < a.max_per_prompt:
            bucket.append(g["out"])
    counts = {"verdicts": dict(finals)}
    for split, by_idx in pairs.items():
        n = 0
        with open(os.path.join(a.out, f"pairs-{split}.jsonl"), "w") as f:
            for idx, rejected in sorted(by_idx.items()):
                msgs = rows[split][idx]
                for r in rejected:
                    f.write(json.dumps({"prompt": msgs[:-1], "chosen": msgs[-1]["content"], "rejected": r},
                                       ensure_ascii=False) + "\n")
                    n += 1
        counts[split] = {"pairs": n, "prompts": len(by_idx), "prompts_total": len(rows[split])}
    json.dump(counts, open(os.path.join(a.out, "pairs-counts.json"), "w"), indent=1)
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
