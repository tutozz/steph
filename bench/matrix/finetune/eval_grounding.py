"""Évalue hors ligne le garde-fou d'ancrage (steph.grounding.ground), sans toucher au flux parlé.

    python bench/matrix/finetune/eval_grounding.py

Deux mesures :

1. Inventions confirmées (judge-*.json, corrigées par judge_audit.v2.json quand
   disponible) : le filtre retire-t-il, du texte jugé, le fait que le juge a signalé comme
   fabriqué ? Détection par le passage entre guillemets « » du champ "note" quand il
   existe, sinon par simple différence avant/après.
2. Faits vrais des sorties réelles (les i5-*.json de bench/matrix/results/finetune,
   36 cas chacun) : le filtre coupe-t-il par erreur un fait juste ? Mesuré par le score
   v2 (rescore.py / facts.v2.json) case par case, avant et après filtrage.

Écrit bench/matrix/results/finetune/grounding/report.json.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

MATRIX = Path(__file__).parent.parent  # bench/matrix
RESULTS = MATRIX / "results" / "finetune"
OUT_DIR = RESULTS / "grounding"

sys.path.insert(0, str(MATRIX))
sys.path.insert(0, str(MATRIX.parent.parent / "src"))

from rescore import score_case  # noqa: E402
from score import HOLDOUT, clean  # noqa: E402
from steph.grounding import ground  # noqa: E402

CASES_BY_ID = {c["id"]: c for c in json.load(open(MATRIX / "cases.json"))}
FACTS_V2 = json.load(open(MATRIX / "facts.v2.json"))
AUDIT = json.load(open(MATRIX / "judge_audit.v2.json"))

JUDGE_FILES = ["judge-fixed.json", "judge-i5.json", "judge-judged.json", "judge-soup.json"]
I5_FILES = sorted(p.name for p in RESULTS.glob("i5-*.json"))


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def input_text_for(case_id: str) -> str | None:
    case = CASES_BY_ID.get(case_id)
    if not case:
        return None
    for m in case["messages"]:
        if m["role"] == "user":
            return m["content"]
    return None


def is_qa(case_id: str) -> bool:
    case = CASES_BY_ID.get(case_id)
    return bool(case) and case.get("kind") == "qa"


def quoted_spans(note: str | None) -> list[str]:
    if not note:
        return []
    return re.findall(r"«\s*([^»]+?)\s*»", note)


# ---------------------------------------------------------------- Partie 1 : inventions


def eval_inventions() -> dict:
    rows = []
    for jf in JUDGE_FILES:
        path = RESULTS / jf
        if not path.exists():
            continue
        data = json.load(open(path))
        for model, info in data["par_modele"].items():
            overrides = AUDIT.get(jf, {}).get(model, {})
            for case in info.get("cas_inventions", []):
                case_id = case["id"]
                verdict = overrides.get(case_id, {}).get("v2", "confirmee")
                if verdict in ("faux_positif", "discutable"):
                    continue  # l'audit humain dit que ce n'est pas (ou pas clairement) une invention
                input_text = input_text_for(case_id)
                if input_text is None:
                    rows.append({"judge_file": jf, "model": model, "id": case_id,
                                 "skipped": "id absent de cases.json"})
                    continue
                phrase = case["phrase"]
                qa = is_qa(case_id)
                filtered = ground(input_text, phrase, is_qa=qa)
                spans = quoted_spans(case.get("note"))
                if qa and filtered == "Pas dans l'historique.":
                    removed, method = True, "qa_introuvable"
                elif spans:
                    removed = all(_fold(s) not in _fold(filtered) for s in spans)
                    method = "guillemets"
                else:
                    removed = filtered.strip() != phrase.strip()
                    method = "heuristique (pas de guillemets dans la note)"
                rows.append({
                    "judge_file": jf, "model": model, "id": case_id,
                    "categorie": case.get("categorie"), "note": case.get("note"),
                    "phrase": phrase, "filtered": filtered,
                    "removed": removed, "method": method,
                })

    tested = [r for r in rows if "skipped" not in r]
    removed = [r for r in tested if r["removed"]]
    by_cat: dict[str, dict[str, int]] = {}
    for r in tested:
        cat = r.get("categorie") or "sans_categorie"
        by_cat.setdefault(cat, {"total": 0, "retirees": 0})
        by_cat[cat]["total"] += 1
        if r["removed"]:
            by_cat[cat]["retirees"] += 1

    return {
        "total_confirmees": len(tested),
        "retirees": len(removed),
        "non_retirees": len(tested) - len(removed),
        "skipped": len(rows) - len(tested),
        "par_categorie": by_cat,
        "detail_non_retirees": [r for r in tested if not r["removed"]],
    }


# --------------------------------------------------------- Partie 2 : faits vrais / v2


def quality(pairs: list[tuple[str, float]], split: str = "all") -> float | None:
    if split == "tune":
        pairs = [p for p in pairs if p[0] not in HOLDOUT]
    elif split == "holdout":
        pairs = [p for p in pairs if p[0] in HOLDOUT]
    vals = [v for _, v in pairs if v == v]
    return round(100 * sum(vals) / len(vals), 1) if vals else None


def eval_file(name: str) -> dict:
    data = json.load(open(RESULTS / name))
    rows = [r for r in data.get("rows") or [] if r.get("out") is not None]
    before, after, regressions, gains = [], [], [], []
    for row in rows:
        fixture, kind, case_id = row["fixture"], row["kind"], row["id"]
        input_text = input_text_for(case_id)
        cleaned = clean(row["out"])
        if input_text is None:
            continue
        filtered = ground(input_text, cleaned, is_qa=(kind == "qa"))
        s_before = score_case(FACTS_V2, fixture, kind, cleaned)
        s_after = score_case(FACTS_V2, fixture, kind, filtered)
        before.append((fixture, s_before))
        after.append((fixture, s_after))
        if s_before == s_before and s_after == s_after and s_after < s_before:
            regressions.append({"id": case_id, "before": row["out"], "cleaned": cleaned,
                                 "filtered": filtered, "score_before": s_before, "score_after": s_after})
        elif s_before == s_before and s_after == s_after and s_after > s_before:
            gains.append({"id": case_id, "cleaned": cleaned, "filtered": filtered,
                           "score_before": s_before, "score_after": s_after})
    return {
        "file": name, "n": len(rows),
        "v2_before": quality(before), "v2_after": quality(after),
        "v2_before_tune": quality(before, "tune"), "v2_after_tune": quality(after, "tune"),
        "v2_before_holdout": quality(before, "holdout"), "v2_after_holdout": quality(after, "holdout"),
        "faits_vrais_coupes": len(regressions), "gains": len(gains),
        "detail_faux_positifs": regressions,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    inventions = eval_inventions()
    files = [eval_file(name) for name in I5_FILES]
    flagship = next(f for f in files if f["file"] == "i5-soup-granite-uniform-Q4_K_M.json")

    total_cases = sum(f["n"] for f in files)
    total_regressions = sum(f["faits_vrais_coupes"] for f in files)

    report = {
        "inventions": inventions,
        "faits_vrais": {
            "fichier_reference": flagship,
            "tous_les_i5": files,
            "total_cas": total_cases,
            "total_faits_vrais_coupes": total_regressions,
        },
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))

    print(f"Inventions confirmées testées : {inventions['total_confirmees']} "
          f"(skipped {inventions['skipped']})")
    print(f"  retirées   : {inventions['retirees']}")
    print(f"  non retirées : {inventions['non_retirees']}")
    print()
    print("| fichier | n | v2 avant | v2 après | faits vrais coupés | gains |")
    print("|---|---|---|---|---|---|")
    for f in files:
        print(f"| {f['file']} | {f['n']} | {f['v2_before']} | {f['v2_after']} "
              f"| {f['faits_vrais_coupes']} | {f['gains']} |")
    print()
    print(f"Total : {total_regressions} faits vrais coupés sur {total_cases} cas "
          f"({len(files)} fichiers i5-*.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
