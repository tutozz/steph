#!/usr/bin/env python3
"""Juge les sorties générées par gen_outputs.py, 2 passes (A puis B), méthode A7 (P16).

    PYTHONPATH=<dossier de judge_lib.py> python3 judge_outputs.py --data <dossier> --gen gen.jsonl \
        --out verdicts.jsonl

Une sortie identique à l'étiquette (casse et espaces ignorés) n'est pas jugée : l'étiquette a déjà
passé le juge en A11. Reprise automatique par empreinte (entrée + sortie). Le fichier de verdicts
contient du corpus : il reste sur la machine.

SPDX-License-Identifier: MIT
"""

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from judge_lib import call_judge


def norm(text):
    return " ".join(text.lower().split())


def key(context, phrase):
    return hashlib.sha256((context + "\x00" + phrase).encode()).hexdigest()


def judge(context, phrase, pass_id, retries=2):
    res = None
    for _ in range(retries + 1):
        try:
            res = call_judge(context, phrase, pass_id=pass_id, timeout=300)
        except Exception as e:
            res = {"verdict": "erreur", "inventions": [], "_error": str(e)}
        if res["verdict"] in ("ok", "invention"):
            break
        time.sleep(2)
    return {"verdict": res["verdict"], "inventions": res.get("inventions", [])}


def both(context, phrase):
    return judge(context, phrase, "A"), judge(context, phrase, "B")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--gen", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--parallel", type=int, default=4)
    a = ap.parse_args()

    rows = {s: [json.loads(l)["messages"] for l in open(os.path.join(a.data, f"{s}.jsonl"))] for s in ("train", "val")}
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["key"] for l in open(a.out)}
    todo, skipped = {}, 0
    for line in open(a.gen):
        g = json.loads(line)
        msgs = rows[g["split"]][g["idx"]]
        context, label = msgs[1]["content"], msgs[2]["content"]
        if not g["out"] or norm(g["out"]) == norm(label):
            skipped += 1
            continue
        k = key(context, g["out"])
        if k not in done:
            todo[k] = (context, g["out"])
    print(f"{len(todo)} sorties à juger (x2 passes), {len(done)} déjà jugées, {skipped} égales à l'étiquette", flush=True)
    t0 = time.time()
    with open(a.out, "a") as out, ThreadPoolExecutor(max_workers=a.parallel) as ex:
        futs = {ex.submit(both, c, p): k for k, (c, p) in todo.items()}
        for n, fut in enumerate(as_completed(futs), 1):
            pa, pb = fut.result()
            final = "invention" if pa["verdict"] == pb["verdict"] == "invention" else \
                "ok" if pa["verdict"] == pb["verdict"] == "ok" else "douteux"
            out.write(json.dumps({"key": futs[fut], "A": pa, "B": pb, "final": final}, ensure_ascii=False) + "\n")
            out.flush()
            if n % 100 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
