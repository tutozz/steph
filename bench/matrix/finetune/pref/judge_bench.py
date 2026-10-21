#!/usr/bin/env python3
"""Juge A7 (judge_lib d'origine, 2 passes) sur des résultats de banc 36 cas (P15, P17, P14, K3).

    PYTHONPATH=<dossier du judge_lib A7> python3 judge_bench.py <cases.json> <out.json> <banc1.json> [...] [--ground]

Contexte jugé : premier message utilisateur du cas, comme P15 et P17. `--ground` applique
d'abord steph.grounding.ground() à chaque sortie (entrée : tous les messages utilisateur,
is_qa selon le cas), comme narrator._llm_say en production (P14). Une sortie vidée par
l'ancrage n'est pas jugée (rien n'est dit par le modèle). Écrit les verdicts, imprime les
comptes par fichier.

SPDX-License-Identifier: MIT
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from judge_lib import call_judge

from steph.grounding import ground


def retry(ctx, phrase, pass_id):
    last = None
    for _ in range(3):
        r = call_judge(ctx, phrase, pass_id=pass_id)
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
    name, row, ctx, phrase = task
    if not phrase.strip():
        return {"model_file": name, "id": row["id"], "kind": row["kind"], "phrase": phrase, "final": "vide"}
    a, b = retry(ctx, phrase, "A"), retry(ctx, phrase, "B")
    return {"model_file": name, "id": row["id"], "kind": row["kind"], "phrase": phrase,
            "pass_A": {"verdict": a["verdict"], "inventions": a["inventions"]},
            "pass_B": {"verdict": b["verdict"], "inventions": b["inventions"]},
            "final": final_verdict(a["verdict"], b["verdict"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("out")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--ground", action="store_true")
    a = ap.parse_args()
    cases = {c["id"]: c for c in json.load(open(a.cases))}
    tasks = []
    for f in a.files:
        rows = json.load(open(f))["rows"]
        assert len(rows) == 36, f
        for r in rows:
            users = [m["content"] for m in cases[r["id"]]["messages"] if m["role"] == "user"]
            phrase = r["out"] or ""
            if a.ground:
                phrase = ground("\n".join(users), phrase, is_qa=r["kind"] == "qa")
            tasks.append((os.path.basename(f), r, users[0], phrase))
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, tasks))
    json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)
    summary = {}
    for f in a.files:
        n = os.path.basename(f)
        rs = [r for r in res if r["model_file"] == n]
        summary[n] = {k: sum(r["final"] == k for r in rs) for k in ("invention", "douteux", "erreur", "vide")}
        summary[n]["invention_ids"] = [r["id"] for r in rs if r["final"] == "invention"]
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
