"""Compose the R1 fine-tuning set: the K3 mix unchanged, plus extra rows already filtered by compose_k3.py
(new French and English questions), with per-source weighting of the training split.

    python3 compose_r1.py --base mix-k3 --extra mix-qa-r1 --repeat en_summary=2 --keep detail=0.5 --out mix-r1

- extra rows whose system and user turns already exist in the base are dropped;
- --keep source=fraction keeps that share of the training rows of a source, chosen by a hash of the user turn;
- --repeat source=n writes each training row of a source n times;
- the validation split is never subsampled nor repeated, so validation losses stay comparable with K3.
Only counts are printed, never corpus text.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path


def read(folder: Path, name: str) -> list[dict]:
    return [json.loads(line) for line in (folder / f"{name}.jsonl").open(encoding="utf-8") if line.strip()]


def key(r: dict) -> str:
    return "\x00".join(m["content"] for m in r["messages"][:-1])


def kept(r: dict, fraction: float) -> bool:
    user = "\n".join(m["content"] for m in r["messages"] if m["role"] == "user")
    return int(hashlib.sha256(user.encode()).hexdigest(), 16) % 10_000 < fraction * 10_000


def specs(values: list[str], cast) -> dict:
    return {name: cast(value) for name, value in (v.split("=", 1) for v in values)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--extra", type=Path, required=True)
    ap.add_argument("--repeat", action="append", default=[], help="source=n")
    ap.add_argument("--keep", action="append", default=[], help="source=fraction")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    repeat, keep = specs(args.repeat, int), specs(args.keep, float)

    counts: collections.Counter = collections.Counter()
    split = {}
    for name in ("train", "val"):
        base = read(args.base, name)
        seen = {key(r) for r in base}
        rows = list(base)
        for r in read(args.extra, name):
            if key(r) in seen:
                counts["extra_duplicate"] += 1
                continue
            seen.add(key(r))
            rows.append(r)
            counts[f"extra_{name}"] += 1
        split[name] = rows

    train = []
    for r in split["train"]:
        if r["source"] in keep and not kept(r, keep[r["source"]]):
            counts["dropped_by_keep"] += 1
            continue
        train += [r] * repeat.get(r["source"], 1)
    split["train"] = train

    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in split.items():
        with (args.out / f"{name}.jsonl").open("w", encoding="utf-8") as out:
            out.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    report = dict(counts)
    report["train_by_source"] = dict(sorted(collections.Counter(r["source"] for r in split["train"]).items()))
    report["val_by_source"] = dict(sorted(collections.Counter(r["source"] for r in split["val"]).items()))
    report["train"], report["val"] = len(split["train"]), len(split["val"])
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
