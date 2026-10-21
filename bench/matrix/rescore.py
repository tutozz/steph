"""Recalcule tous les résultats de banc existants avec facts.json (v1) et facts.v2.json (v2).

    python bench/matrix/rescore.py                 -> tableaux Markdown avant/après
    python bench/matrix/rescore.py --json          -> mêmes chiffres en JSON

Qualité : même règle que score.py (sorties nettoyées), seul le fichier de faits change.
Inventions : comptes du juge IA (judge-*.json), corrigés par judge_audit.v2.json.
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from score import HOLDOUT, clean, plain  # noqa: E402

RESULTS = HERE / "results" / "finetune"


def load_facts(path) -> dict:
    return json.load(open(path))


def score_case(facts: dict, fixture: str, kind: str, out: str) -> float:
    spec = facts.get(fixture)
    if not spec:
        return float("nan")
    text = plain(out)
    if any(re.search(p, text) for p in facts["_global_never"] + spec.get("never", [])):
        return 0.0
    need = spec["need"]
    s = sum(bool(re.search(p, text)) for p in need) / len(need)
    if len(out.split()) > facts["_max_words"][kind]:
        s *= 0.8
    return s


def quality(facts: dict, rows: list, split: str = "all"):
    if split == "tune":
        rows = [r for r in rows if r["fixture"] not in HOLDOUT]
    elif split == "holdout":
        rows = [r for r in rows if r["fixture"] in HOLDOUT]
    scores = [score_case(facts, r["fixture"], r["kind"], clean(r["out"])) for r in rows]
    scores = [s for s in scores if s == s]
    return round(100 * sum(scores) / len(scores), 1) if scores else None


def rescore_file(path, v1: dict, v2: dict) -> dict:
    r = json.load(open(path))
    rows = [row for row in r.get("rows") or [] if row.get("out") is not None]
    out = {"file": Path(path).name, "label": r.get("label"), "n": len(rows)}
    for name, facts in (("v1", v1), ("v2", v2)):
        out[name] = quality(facts, rows)
        out[f"{name}_tune"] = quality(facts, rows, "tune")
        out[f"{name}_holdout"] = quality(facts, rows, "holdout")
    return out


def judge_counts(model: dict, overrides: dict) -> dict:
    ids = [c["id"] for c in model.get("cas_inventions", [])]
    verdicts = [overrides.get(i, {}).get("v2", "confirmee") for i in ids]
    total = model["invention_sur_36"]
    false_pos, debatable = verdicts.count("faux_positif"), verdicts.count("discutable")
    return {"v1": total, "v2": total - false_pos - debatable, "v2_with_debatable": total - false_pos}


def ranks(rows: list, key: str) -> dict:
    ordered = sorted((r for r in rows if r[key] is not None), key=lambda r: -r[key])
    return {r["file"]: i + 1 for i, r in enumerate(ordered)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--v1", default=str(HERE / "facts.json"))
    ap.add_argument("--v2", default=str(HERE / "facts.v2.json"))
    ap.add_argument("--audit", default=str(HERE / "judge_audit.v2.json"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    v1, v2 = load_facts(a.v1), load_facts(a.v2)

    files = sorted(p for p in RESULTS.glob("*.json") if not p.name.startswith("judge-"))
    rows = [rescore_file(p, v1, v2) for p in files]
    rows = [r for r in rows if r["n"]]
    r1, r2 = ranks(rows, "v1"), ranks(rows, "v2")

    audit = load_facts(a.audit) if Path(a.audit).exists() else {}
    judged = []
    for jf in sorted(RESULTS.glob("judge-*.json")):
        for model, v in json.load(open(jf))["par_modele"].items():
            judged.append({"judge": jf.name, "model": model,
                           **judge_counts(v, audit.get(jf.name, {}).get(model, {}))})

    if a.json:
        print(json.dumps({"quality": rows, "inventions": judged}, ensure_ascii=False, indent=1))
        return 0
    print("| Résultat | n | v1 | v2 | écart | rang v1 | rang v2 | tune v1/v2 | holdout v1/v2 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: -(r["v2"] or 0)):
        delta = round(r["v2"] - r["v1"], 1)
        print(f"| {r['file'].removesuffix('.json')} | {r['n']} | {r['v1']} | {r['v2']} | {delta:+} "
              f"| {r1[r['file']]} | {r2[r['file']]} | {r['v1_tune']}/{r['v2_tune']} "
              f"| {r['v1_holdout']}/{r['v2_holdout']} |")
    print()
    print("| Juge | Modèle | inventions v1 | v2 confirmées | v2 avec discutables |")
    print("|---|---|---|---|---|")
    for j in sorted(judged, key=lambda j: j["v2"]):
        print(f"| {j['judge']} | {j['model'].removesuffix('.json')} | {j['v1']} | {j['v2']} | {j['v2_with_debatable']} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
