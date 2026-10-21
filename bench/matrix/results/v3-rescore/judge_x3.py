#!/usr/bin/env python3
"""X3 : juge A7 (judge_v3.one, 2 passes) sur les seules réponses que steph envoie au modèle
(reaches_model), sans rejuger une réponse déjà jugée sur le même contexte.

    JUDGE_PORT=<port> PYTHONPATH=<judge_lib A7>:<bench/matrix/v3/tools> \\
        python3 judge_x3.py <harness.json> <out.json> <run.json> --cache <verdicts dir> [--threads 8]

Cache : tous les inv-*.json du dossier ; clé = (contexte jugé, réponse). Une réponse identique
reprend le verdict (champ "reused" = fichier d'origine). Sortie au format de judge_v3.py, reprenable.

SPDX-License-Identifier: MIT
"""

import argparse
import glob
import json
import os
from concurrent.futures import ThreadPoolExecutor

import judge_lib
import judge_v3

judge_lib.URL = f"http://127.0.0.1:{os.environ['JUDGE_PORT']}/v1/chat/completions"


def load_cache(d):
    cache = {}
    for p in glob.glob(os.path.join(d, "inv-*.json")):
        for v in json.load(open(p)):
            if v["final"] != "erreur" and "harness" in v:
                cache.setdefault((v["harness"], v["id"], v["phrase"]), {**v, "origin": os.path.basename(p)})
    return cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("harness")
    ap.add_argument("out")
    ap.add_argument("run")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    hname = os.path.basename(a.harness)
    harness = {c["id"]: c for c in json.load(open(a.harness))}
    cache = load_cache(a.cache)
    name = os.path.basename(a.run)
    done = json.load(open(a.out)) if os.path.exists(a.out) else []
    done = [r for r in done if r["final"] != "erreur"]
    seen = {r["id"] for r in done}
    tasks, reused = [], 0
    for r in json.load(open(a.run))["rows"]:
        if r["id"] in seen or r.get("out") is None or not harness[r["id"]]["reaches_model"]:
            continue
        hit = cache.get((hname, r["id"], r["out"]))
        if hit:
            done.append({**{k: hit[k] for k in ("id", "phrase", "final") if k in hit},
                         **{k: hit[k] for k in ("pass_A", "pass_B") if k in hit},
                         "model_file": name, "harness": hname, "reused": hit["origin"]})
            reused += 1
            continue
        tasks.append((name, r["id"], judge_v3.judge_context(harness[r["id"]]["messages"]), r["out"]))
    print(f"{name}: {len(tasks)} à juger, {reused} repris du cache", flush=True)
    with ThreadPoolExecutor(a.threads) as ex:
        for i, res in enumerate(ex.map(judge_v3.one, tasks), 1):
            done.append({**res, "harness": hname})
            if i % 50 == 0 or i == len(tasks):
                json.dump(done, open(a.out, "w"), ensure_ascii=False)
                print(f"{i}/{len(tasks)}", flush=True)
    json.dump(done, open(a.out, "w"), ensure_ascii=False)
    print(json.dumps({k: sum(r["final"] == k for r in done) for k in ("invention", "douteux", "erreur", "vide", "ok")}))


if __name__ == "__main__":
    main()
