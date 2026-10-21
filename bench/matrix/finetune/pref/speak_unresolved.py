#!/usr/bin/env python3
"""Steph Speak Bench, part non résolue en code (P14, K3) : score run.py et inventions au juge A7.

    PYTHONPATH=<src steph>:<dossier du judge_lib A7> python3 speak_unresolved.py <résultat run.py> [...] \\
        --data benchmark/data/v1 [--judge]

Cas retenus : ceux où steph.digest.resolve() ne répond pas, recalculé avec le code actuel,
ou la liste fixe `--ids` (P14 : 14 cas, dont tests-mocha-vitest que resolve() couvre depuis). Contexte jugé : le message
utilisateur que run.py a réellement envoyé (build_messages de run.py). Imprime, par fichier,
n, score moyen (%), inventions, douteux et identifiants.

SPDX-License-Identifier: MIT
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from steph.digest import resolve

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "benchmark"))
import run as speak  # noqa: E402


def unresolved(cases):
    return {c["id"] for c in cases if c["task"] == "summary" and resolve(c["cmd"], c["exit"], c["output"], c["lang"]) is None}


def judged(ctx, phrase):
    from judge_lib import call_judge

    verdicts = []
    for pass_id in ("A", "B"):
        r = None
        for _ in range(3):
            r = call_judge(ctx, phrase, pass_id=pass_id)
            if r["verdict"] in ("ok", "invention"):
                break
            time.sleep(1)
        verdicts.append(r["verdict"])
    if verdicts == ["invention", "invention"]:
        return "invention"
    return "douteux" if "invention" in verdicts else ("erreur" if "erreur" in verdicts else "ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+")
    ap.add_argument("--data", default=str(REPO / "benchmark/data/v1"))
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--ids", default="", help="liste fixe d'identifiants (virgules), ex. les 14 cas de P14")
    a = ap.parse_args()
    config = speak.load_config(Path(a.data))
    out = {}
    for path in a.results:
        res = json.load(open(path))
        cases = {c["id"]: c for c in speak.load_cases(Path(a.data), res["lang"], res["split"])}
        keep = set(a.ids.split(",")) if a.ids else unresolved(cases.values())
        rows = [r for r in res["rows"] if r["id"] in keep]
        entry = {"lang": res["lang"], "n": len(rows), "score_pct": round(100 * statistics.mean(r["score"] for r in rows), 1)}
        if a.judge:
            verdicts = {}
            for r in rows:
                ctx = speak.build_messages(cases[r["id"]], config["prompts"])[1]["content"]
                verdicts[r["id"]] = judged(ctx, r["answer"] or "") if (r["answer"] or "").strip() else "vide"
            entry.update({k: sum(v == k for v in verdicts.values()) for k in ("invention", "douteux", "erreur")})
            entry["invention_ids"] = sorted(i for i, v in verdicts.items() if v == "invention")
        out[Path(path).name] = entry
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
