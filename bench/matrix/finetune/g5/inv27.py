#!/usr/bin/env python3
"""G5 : contre-jugement 27B des évaluations discordantes au juge A7 9B, méthode du juge du tour 3 (a27.py).

    python3 inv27.py build <harness.json> <verd9-a.json> <verd9-b.json> <run-a.json> <run-b.json> <tasks.json>
    python3 inv27.py analyze <tasks.json> <v27.jsonl> <out.json>

Discordant = une réponse inventée au 9B (les deux passes), l'autre non, sur une même évaluation reaches_model.
Les tâches (format b1_judge.py : key, id, ctx, phrase) sont rangées par sha256("g5-27b:" + id), ordre de jugement :
un arrêt laisse un préfixe. Écart 27B = moyenne sur les évaluations discordantes finies de (a - b) x |D| / N ;
les concordantes comptent 0 (hypothèse non vérifiée, comme au tour 3). Même calcul au 9B sur le même sous-échantillon.

SPDX-License-Identifier: MIT
"""

import hashlib
import json
import sys

import numpy as np


def ctx_of(h):
    return "\n\n".join(m["content"] for m in h["messages"] if m["role"] == "user")


def key(ctx, phrase):
    return hashlib.sha256((ctx + "\x00" + phrase).encode()).hexdigest()[:20]


def build(hp, va, vb, ra, rb, out):
    harness = {c["id"]: c for c in json.load(open(hp))}
    v9 = [{x["id"]: x["final"] for x in json.load(open(p))} for p in (va, vb)]
    runs = [{r["id"]: r.get("out") for r in json.load(open(p))["rows"]} for p in (ra, rb)]
    reach = [i for i, h in harness.items() if h["reaches_model"]]
    ok = [i for i in reach if all(i in v and v[i] != "erreur" for v in v9) and all(r.get(i) for r in runs)]
    disc = [i for i in ok if (v9[0][i] == "invention") != (v9[1][i] == "invention")]
    disc.sort(key=lambda i: hashlib.sha256(("g5-27b:" + i).encode()).hexdigest())
    tasks, refs = {}, []
    for i in disc:
        ctx = ctx_of(harness[i])
        for side, r, v in (("a", runs[0], v9[0]), ("b", runs[1], v9[1])):
            k = key(ctx, r[i])
            refs.append({"side": side, "id": i, "key": k, "v9": v[i]})
            tasks.setdefault(k, {"key": k, "id": i, "ctx": ctx, "phrase": r[i]})
    # interleave by evaluation so that a prefix of the task list covers whole evaluations
    order = {k: n for n, k in enumerate(dict.fromkeys(r["key"] for r in refs))}
    json.dump({"n_eval": len(ok), "discordant": disc, "tasks": sorted(tasks.values(), key=lambda t: order[t["key"]]),
               "refs": refs}, open(out, "w"), ensure_ascii=False)
    print(json.dumps({"reaches_model": len(reach), "evaluations": len(ok), "discordant": len(disc), "tasks": len(tasks)}))


def analyze(tp, vp, out):
    t = json.load(open(tp))
    v27 = {}
    for line in open(vp):
        r = json.loads(line)
        if r["final"] != "erreur":
            v27[r["key"]] = r["final"]
    ref = {(r["side"], r["id"]): r for r in t["refs"]}
    done = [i for i in t["discordant"] if all(ref[(s, i)]["key"] in v27 for s in "ab")]
    inv27 = lambda s, i: float(v27[ref[(s, i)]["key"]] == "invention")  # noqa: E731
    inv9 = lambda s, i: float(ref[(s, i)]["v9"] == "invention")  # noqa: E731
    d27 = np.array([inv27("a", i) - inv27("b", i) for i in done])
    d9 = np.array([inv9("a", i) - inv9("b", i) for i in done])
    scale = 100 * len(t["discordant"]) / t["n_eval"]
    rng = np.random.default_rng(20260929)
    idx = rng.integers(0, len(done), size=(10_000, len(done)))

    def est(d):
        bs = d[idx].mean(axis=1) * scale
        return {"diff": round(float(d.mean() * scale), 2),
                "ci95": [round(float(np.percentile(bs, 2.5)), 2), round(float(np.percentile(bs, 97.5)), 2)]}

    agree = np.mean([(inv27(s, i) == 1) == (inv9(s, i) == 1) for i in done for s in "ab"])
    res = {"evaluations": t["n_eval"], "discordant": len(t["discordant"]), "judged": len(done),
           "diff_27b": est(d27), "diff_9b_same_subset": est(d9), "shift_27b_minus_9b": est(d27 - d9),
           "inventions_27b": {"a": int(sum(inv27("a", i) for i in done)), "b": int(sum(inv27("b", i) for i in done))},
           "agreement_9b_27b_pct": round(100 * float(agree), 1)}
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res))


if __name__ == "__main__":
    {"build": build, "analyze": analyze}[sys.argv[1]](*sys.argv[2:])
