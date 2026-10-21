#!/usr/bin/env python3
"""A7 invention judge (2 passes) over bench v3 runs; the bench v3 counterpart of judge_bench.py.

    PYTHONPATH=<A7 judge_lib dir> python3 judge_v3.py <harness.json> <out.json> <run.json> [...] [--threads 4]

Context judged: the user message of the harness row, as judge_bench.py does. Final verdict per
answer: invention if both passes say so, douteux if one does, erreur if a pass failed three times.
Empty answers are not judged; a request the server refuses (HTTP 400, context beyond the slot) ends
as erreur and is excluded from the counts. Resumable: verdicts already in <out.json> are kept.

SPDX-License-Identifier: MIT
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from judge_lib import call_judge


def retry(ctx, phrase, pass_id):
    last = None
    for _ in range(3):
        try:
            r = call_judge(ctx, phrase, pass_id=pass_id)
        except Exception as e:  # e.g. HTTP 400 when the context exceeds the server slot
            r = {"inventions": [], "verdict": "erreur", "_error": str(e)[:200]}
        if r["verdict"] in ("ok", "invention"):
            return r
        last = r
        time.sleep(1)
    return last


def final_verdict(va, vb):
    if va == vb == "invention":
        return "invention"
    if "invention" in (va, vb):
        return "douteux"
    return "erreur" if "erreur" in (va, vb) else "ok"


def one(task):
    name, rid, ctx, phrase = task
    if not phrase.strip():
        return {"model_file": name, "id": rid, "phrase": phrase, "final": "vide"}
    a, b = retry(ctx, phrase, "A"), retry(ctx, phrase, "B")
    return {"model_file": name, "id": rid, "phrase": phrase,
            "pass_A": {"verdict": a["verdict"], "inventions": a["inventions"]},
            "pass_B": {"verdict": b["verdict"], "inventions": b["inventions"]},
            "final": final_verdict(a["verdict"], b["verdict"])}


def judge_context(messages):
    """Ce que le modèle a lu : un résumé n'a qu'un message utilisateur ; une question en a deux,
    l'historique puis la question (format de production P20)."""
    return "\n\n".join(m["content"] for m in messages if m["role"] == "user")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("harness")
    ap.add_argument("out")
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    harness = {c["id"]: c for c in json.load(open(a.harness))}
    done = json.load(open(a.out)) if os.path.exists(a.out) else []
    seen = {(r["model_file"], r["id"]) for r in done if r["final"] != "erreur"}
    done = [r for r in done if (r["model_file"], r["id"]) in seen]
    tasks = []
    for f in a.runs:
        name = os.path.basename(f)
        for r in json.load(open(f))["rows"]:
            if (name, r["id"]) in seen or r.get("out") is None:
                continue
            tasks.append((name, r["id"], judge_context(harness[r["id"]]["messages"]), r["out"]))
    with ThreadPoolExecutor(a.threads) as ex:
        for i, res in enumerate(ex.map(one, tasks), 1):
            done.append(res)
            if i % 50 == 0 or i == len(tasks):
                json.dump(done, open(a.out, "w"), ensure_ascii=False)
                print(f"{i}/{len(tasks)}", flush=True)
    json.dump(done, open(a.out, "w"), ensure_ascii=False)
    summary = {}
    for f in a.runs:
        n = os.path.basename(f)
        rs = [r for r in done if r["model_file"] == n]
        summary[n] = {k: sum(r["final"] == k for r in rs) for k in ("invention", "douteux", "erreur", "vide", "ok")}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
