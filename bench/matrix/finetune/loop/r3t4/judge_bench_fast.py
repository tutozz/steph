#!/usr/bin/env python3
"""Juge A7 (2 passes) sur des runs du banc v3, accéléré : judge_v3.py sans rien de ce qui ne compte pas.

    PYTHONPATH=<judge_lib A7>:<ce dossier> JUDGE_PORT=8977 python3 judge_bench_fast.py judge \
        --harness dev.json --cache cache/ --shard 0 --nshards 2 runs/*.json
    python3 judge_bench_fast.py merge --harness dev.json --cache cache/ --out verdicts.json runs/*.json

- seules les réponses où `reaches_model` est vrai sont jugées : les autres, steph les dit en code ;
- une réponse identique octet pour octet pour le même cas n'est jugée qu'une fois, quels que
  soient le modèle et la graine (cache par empreinte cas + réponse) ;
- la liste des réponses distinctes est découpée en parts disjointes, une par serveur juge ;
- merge écrit le format de judge_v3.py (model_file, id, phrase, pass_A, pass_B, final), lu par
  power_v3.py --judge.

SPDX-License-Identifier: MIT
"""

import argparse
import collections
import glob
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mask_pairs import cache_key, call_retry, final_verdict, judge_context, shard


def answers(harness, runs):
    """[(run name, row id, answer)] des réponses non vides qui atteignent le modèle."""
    out, skipped = [], collections.Counter()
    for f in runs:
        name = Path(f).name
        for r in json.load(open(f))["rows"]:
            if r.get("out") is None or not r["out"].strip():
                skipped["empty"] += 1
            elif not harness[r["id"]].get("reaches_model", True):
                skipped["no_model"] += 1
            else:
                out.append((name, r["id"], r["out"]))
    return out, skipped


def load_cache(folder):
    out = {}
    for p in sorted(glob.glob(str(Path(folder) / "bench-*.jsonl"))):
        for line in open(p, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                if r["final"] != "erreur":
                    out[r["key"]] = r
    return out


def judge(a, harness):
    rows, skipped = answers(harness, a.runs)
    unique = {cache_key(rid, text): (rid, text) for _, rid, text in rows}
    done = load_cache(a.cache)
    todo = [k for k in shard(sorted(unique), a.shard, a.nshards) if k not in done]
    Path(a.cache).mkdir(parents=True, exist_ok=True)
    out = Path(a.cache) / f"bench-{a.shard}.jsonl"
    print(json.dumps({"answers": len(rows), "unique": len(unique), "skipped": dict(skipped),
                      "shard_todo": len(todo)}), flush=True)
    t0, counter = time.time(), collections.Counter()

    def work(k):
        rid, text = unique[k]
        ctx = judge_context(harness[rid]["messages"])
        va, vb = call_retry(ctx, text, "A"), call_retry(ctx, text, "B")
        return {"key": k, "id": rid, "phrase": text,
                "pass_A": {"verdict": va["verdict"], "inventions": va.get("inventions", [])},
                "pass_B": {"verdict": vb["verdict"], "inventions": vb.get("inventions", [])},
                "final": final_verdict(va["verdict"], vb["verdict"])}

    with ThreadPoolExecutor(a.threads) as pool, out.open("a", encoding="utf-8") as f:
        for i, r in enumerate(pool.map(work, todo), 1):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            counter[r["final"]] += 1
            if i % 100 == 0 or i == len(todo):
                print(json.dumps({"done": i, "todo": len(todo), **counter, "s": round(time.time() - t0)}), flush=True)


def merge(a, harness):
    rows, skipped = answers(harness, a.runs)
    cache = load_cache(a.cache)
    verdicts, missing = [], 0
    for name, rid, text in rows:
        c = cache.get(cache_key(rid, text))
        if c is None:
            missing += 1
            continue
        verdicts.append({"model_file": name, "id": rid, "phrase": text, "pass_A": c["pass_A"],
                         "pass_B": c["pass_B"], "final": c["final"]})
    json.dump(verdicts, open(a.out, "w"), ensure_ascii=False)
    summary = {Path(f).name: dict(collections.Counter(v["final"] for v in verdicts if v["model_file"] == Path(f).name))
               for f in a.runs}
    print(json.dumps({"verdicts": len(verdicts), "missing": missing, "skipped": dict(skipped),
                      "unique_judged": len(cache), "by_run": summary}, ensure_ascii=False))
    if missing:
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["judge", "merge"])
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--harness", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--out")
    a = ap.parse_args()
    harness = {c["id"]: c for c in json.load(open(a.harness))}
    (judge if a.cmd == "judge" else merge)(a, harness)


if __name__ == "__main__":
    main()
