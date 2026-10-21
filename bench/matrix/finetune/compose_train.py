"""Build the fine-tuning set from the finalized labels, deterministically.

    python3 compose_train.py final/train.jsonl out_dir [--cap 120] [--bench cases.json ...] [--exclude rejects.txt]

Keeps every row of the final corpus, tops up with instantané rows only while a program stays
under the cap, drops exact duplicates, rows whose user-message sha256 is listed in --exclude
(labels the AI judge found inventive) and anything sharing output lines with a bench case,
then splits 95 / 5 into train and validation by a hash of the user message.

SPDX-License-Identifier: MIT
"""

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path

WRAPPERS = {"sudo", "timeout", "env", "nice", "-n"}


def program(row: dict) -> str:
    m = re.search(r"Commande : (.*)", row["messages"][1]["content"])
    words = [w for w in (m.group(1).split() if m else []) if "=" not in w and w not in WRAPPERS]
    return words[0].rsplit("/", 1)[-1] if words else "?"


def output_lines(text: str) -> set[str]:
    out = text.split("Sortie :\n", 1)[-1]
    return {line.strip() for line in out.splitlines() if len(line.strip()) >= 24}


def bench_lines(paths: list[Path]) -> set[str]:
    lines = set()
    for p in paths:
        for case in json.loads(p.read_text()):
            lines |= output_lines(case["messages"][-1]["content"])
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("train", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--cap", type=int, default=120, help="exemples au plus par programme")
    ap.add_argument("--bench", type=Path, nargs="*", default=[])
    ap.add_argument("--exclude", type=Path, help="empreintes sha256 du message utilisateur à écarter")
    args = ap.parse_args()

    rows = [json.loads(line) for line in args.train.open()]
    # final corpus first, so the instantané only fills programs the corpus left thin
    rows.sort(key=lambda r: r["source"].startswith("snapshot"))
    banned = bench_lines(args.bench)
    excluded = set(args.exclude.read_text().split()) if args.exclude else set()
    counts, seen, kept = collections.Counter(), set(), []
    stats = collections.Counter()
    for r in rows:
        user = r["messages"][1]["content"]
        prog = program(r)
        if user in seen:
            stats["doublon"] += 1
            continue
        if excluded and hashlib.sha256(user.encode()).hexdigest() in excluded:
            stats["rejet juge"] += 1
            continue
        if banned and len(output_lines(user) & banned) >= 2:
            stats["contamination banc"] += 1
            continue
        if r["source"].startswith("snapshot") and counts[prog] >= args.cap:
            stats["plafond programme"] += 1
            continue
        seen.add(user)
        counts[prog] += 1
        kept.append(r)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    split = {"train": [], "val": []}
    for r in kept:
        h = int(hashlib.sha256(r["messages"][1]["content"].encode()).hexdigest(), 16)
        split["val" if h % 20 == 0 else "train"].append({"messages": r["messages"]})
    for name, items in split.items():
        with (args.out_dir / f"{name}.jsonl").open("w") as out:
            out.writelines(json.dumps(i, ensure_ascii=False) + "\n" for i in items)
    top = counts.most_common(1)[0]
    print(f"gardés {len(kept)} (train {len(split['train'])}, val {len(split['val'])}) ; écartés {dict(stats)} ; "
          f"{len(counts)} programmes, le plus fréquent {top[0]} {100 * top[1] / len(kept):.1f} %")


if __name__ == "__main__":
    main()
