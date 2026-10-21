"""T9 : juge A7 local (2 passes) sur un échantillon des nouvelles étiquettes, sur la machine du corpus.

    PYTHONPATH=<dossier de judge_lib A7> python3 t9_judge_labels.py --tasks tasks.jsonl --labels relabel-labels.jsonl \\
        --per-task fr_summary=150 en_summary=100 qa=40 progress=30 detail=40 --out judge-labels.jsonl

Contexte jugé : le tour utilisateur de l'enseignant (entrée steph, bloc de faits L5 compris ; historique et
question pour les questions). Verdict final : invention si les deux passes le disent, douteux si une seule.
Graine 9. Seuls des comptes sont imprimés ; le fichier écrit contient du texte de corpus et reste sur place.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random

from judge_lib import call_judge


def final(a: str, b: str) -> str:
    if a == b == "invention":
        return "invention"
    if "invention" in (a, b):
        return "douteux"
    return "erreur" if "erreur" in (a, b) else "ok"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--per-task", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    tasks = {t["tid"]: t for t in map(json.loads, open(a.tasks, encoding="utf-8"))}
    labels = [r for r in map(json.loads, open(a.labels, encoding="utf-8")) if r["label"]]
    rng = random.Random(9)
    chosen = []
    for spec in a.per_task:
        task, n = spec.split("=")
        pool = sorted((r for r in labels if r["task"] == task), key=lambda r: r["tid"])
        chosen += rng.sample(pool, min(int(n), len(pool)))

    def one(r: dict) -> dict:
        ctx = "\n\n".join(m["content"] for m in tasks[r["tid"]]["teacher_messages"] if m["role"] == "user")
        v = {}
        for p in ("A", "B"):
            try:
                v[p] = call_judge(ctx, r["label"], pass_id=p)
            except Exception as e:  # noqa: BLE001
                v[p] = {"verdict": "erreur", "inventions": [], "_error": repr(e)[:100]}
        return {"tid": r["tid"], "task": r["task"], "label": r["label"], "pass_A": v["A"].get("inventions"),
                "pass_B": v["B"].get("inventions"), "final": final(v["A"]["verdict"], v["B"]["verdict"])}

    with concurrent.futures.ThreadPoolExecutor(a.threads) as ex:
        rows = list(ex.map(one, chosen))
    with open(a.out, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    counts: dict = {}
    for r in rows:
        c = counts.setdefault(r["task"], {"n": 0, "ok": 0, "douteux": 0, "invention": 0, "erreur": 0})
        c["n"] += 1
        c[r["final"]] += 1
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
