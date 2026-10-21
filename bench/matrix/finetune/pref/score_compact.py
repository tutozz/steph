#!/usr/bin/env python3
"""Qualité v2 d'un banc granite200 (P15, P17) : total, contrôle, résumé seul, qa0-qa2, et score
« tel que dit » : le statut que steph dit en code (P9) précède la sortie du modèle, dont le mot de
statut de tête est retiré comme dans narrator._drop_leading_status.

    python3 score_compact.py <cases.json> <banc_b7.json> <banc_b42.json> <banc_b123.json>
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from rescore import load_facts, score_case  # noqa: E402
from score import HOLDOUT, clean  # noqa: E402

STATUS_ECHO = re.compile(r"^\s*(Succès|Échec|Success|Failed)\b[.,:]?\s*")
CODE = re.compile(r"\(code (-?\d+)\)")


def spoken(out, user):
    m = CODE.search(user)
    if not m:
        return out
    code = int(m.group(1))
    prefix = "Succès. " if code == 0 else f"Échec, code {code}. "
    return prefix + STATUS_ECHO.sub("", out, count=1)


def mean(xs):
    xs = [x for x in xs if x == x]
    return round(100 * sum(xs) / len(xs), 1) if xs else None


def score_file(facts, cases, path, said):
    rows = [r for r in json.load(open(path))["rows"] if r.get("out") is not None]
    per = {}
    for r in rows:
        out = r["out"]
        if said and r["kind"] != "qa":
            out = spoken(out, [m for m in cases[r["id"]]["messages"] if m["role"] == "user"][0]["content"])
        per[r["id"]] = (r, score_case(facts, r["fixture"], r["kind"], clean(out)))
    return {
        "total": mean([s for _, s in per.values()]),
        "holdout": mean([s for r, s in per.values() if r["fixture"] in HOLDOUT]),
        "summary": mean([s for r, s in per.values() if r["kind"] != "qa"]),
        "qa": {i: round(100 * per[i][1]) for i in ("qa0", "qa1", "qa2") if i in per},
    }


def summarize(facts, cases, paths, said):
    runs = [score_file(facts, cases, p, said) for p in paths]
    avg = {k: round(sum(r[k] for r in runs) / len(runs), 1) for k in ("total", "holdout", "summary")}
    avg["range"] = [min(r["total"] for r in runs), max(r["total"] for r in runs)]
    avg["per_seed"] = [r["total"] for r in runs]
    avg["qa"] = {i: [r["qa"].get(i) for r in runs] for i in ("qa0", "qa1", "qa2")}
    return avg


def main():
    cases = {c["id"]: c for c in json.load(open(sys.argv[1]))}
    facts = load_facts(HERE / "facts.v2.json")
    paths = sys.argv[2:]
    print(json.dumps({"v2": summarize(facts, cases, paths, False), "v2_spoken": summarize(facts, cases, paths, True)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
