#!/usr/bin/env python3
"""Déplie les verdicts dédupliqués de b1_judge.py (une tâche par couple contexte, réponse) en verdicts
par réponse, au format de judge_v3.py lu par power_v3.py : {"model_file", "id", "final"}.

    python3 expand_verdicts.py <tasks.json> <out.json> <verdicts.jsonl> [...]

L'étiquette d'un run passée à `b1_judge.py build` doit être le nom du fichier du run.
Une réponse vide garde le verdict "vide", comme judge_v3.py ; une tâche sans verdict fait échouer.

SPDX-License-Identifier: MIT
"""

import json
import sys


def expand(refs, verdicts):
    rows = []
    for r in refs:
        final = verdicts.get(r["key"], "vide" if r["key"] not in verdicts and r.get("empty") else None)
        if final is None:
            raise SystemExit(f"verdict manquant : {r['model']} {r['id']}")
        rows.append({"model_file": r["model"], "id": r["id"], "final": final})
    return rows


def main():
    tasks_path, out_path, *verdict_paths = sys.argv[1:]
    data = json.load(open(tasks_path))
    judged = {t["key"] for t in data["tasks"]}
    verdicts = {}
    for p in verdict_paths:
        for line in open(p):
            v = json.loads(line)
            if v["final"] != "erreur" or v["key"] not in verdicts:
                verdicts[v["key"]] = v["final"]
    refs = [dict(r, empty=r["key"] not in judged) for r in data["refs"]]
    rows = expand(refs, verdicts)
    json.dump(rows, open(out_path, "w"), ensure_ascii=False)
    counts = {}
    for r in rows:
        counts.setdefault(r["model_file"], {}).setdefault(r["final"], 0)
        counts[r["model_file"]][r["final"]] += 1
    print(json.dumps(counts, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
