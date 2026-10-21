#!/usr/bin/env python3
"""R1 : candidat contre références, même session, règle de décision T5 (docs/loop-ledger.md).

    python3 compare_r1.py <dossier eval> <candidat> <référence> [<référence> ...] > comparaison.json

Lit, pour chaque étiquette L, bench/L-b{7,42,123}.json, judge-L.txt, judge-L-ground.txt et
speak/L/*_L-steph_{fr,en}_test.json. Écrit les résultats par cas (v2 moyenne des 3 graines,
inventions par graine, Steph Speak Bench test) et, pour chaque paire, le bootstrap apparié par
cas de bench_power.py (10 000 tirages) et le test du signe sur les cas discordants, cas
contestés à part.

SPDX-License-Identifier: MIT
"""

import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "loop"))
from bench_power import (CASES, CONTESTED_FACTS, CONTESTED_INVENTIONS, SEEDS, boot_mean_ci,  # noqa: E402
                         sign_test_p, v2_matrix)

# docs/loop-ledger.md, règle T5 : les 11 cas contestés (faits et inventions) sont exclus des critères
CONTESTED = sorted(CONTESTED_FACTS | CONTESTED_INVENTIONS)
CONTESTED_SET = set(CONTESTED)


def invention_sets(path):
    runs = json.load(open(path))
    return [set(runs[k]["invention_ids"]) for k in sorted(runs, key=lambda k: SEEDS.index(k.rsplit("-", 1)[1][:-5]))]


def speak_scores(ev, label, lang):
    f = sorted(glob.glob(str(ev / "speak" / label / f"*_{label}-steph_{lang}_test.json")))[0]
    return {r["id"]: r["score"] for r in json.load(open(f))["rows"]}


def load(ev, label):
    m = v2_matrix([str(ev / "bench" / f"{label}-{s}.json") for s in SEEDS])
    inv = invention_sets(ev / f"judge-{label}.txt")
    ground = invention_sets(ev / f"judge-{label}-ground.txt")
    return {"v2": m, "inv": inv, "ground": ground,
            "speak": {lang: speak_scores(ev, label, lang) for lang in ("fr", "en")}}


def inv_vec(sets, keep):
    return np.array([np.mean([c in s for s in sets]) for c in keep])


def compare(a, b):
    d = np.nanmean(a["v2"], axis=0) - np.nanmean(b["v2"], axis=0)
    mean, lo, hi, _, n = boot_mean_ci(d)
    out = {"v2_diff_pts": round(100 * mean, 1), "v2_ci95_pts": [round(100 * lo, 1), round(100 * hi, 1)],
           "v2_discordant_cases": int(np.sum(np.abs(d) > 1e-9))}
    keep = [c for c in CASES if c not in CONTESTED_SET]
    for key in ("inv", "ground"):
        da = inv_vec(a[key], keep) - inv_vec(b[key], keep)
        pos, neg = int(np.sum(da > 1e-9)), int(np.sum(da < -1e-9))
        out[key] = {"per36_a": round(float(np.mean([len(s) for s in a[key]])), 2),
                    "per36_b": round(float(np.mean([len(s) for s in b[key]])), 2),
                    "per36_a_without_contested": round(float(np.mean([len(s - CONTESTED_SET) for s in a[key]])), 2),
                    "per36_b_without_contested": round(float(np.mean([len(s - CONTESTED_SET) for s in b[key]])), 2),
                    "cases_worse": pos, "cases_better": neg, "sign_test_p": round(sign_test_p(pos, neg), 3),
                    "new_cases_2_of_3_seeds": sorted(c for c in keep
                                                     if sum(c in s for s in a[key]) >= 2 and sum(c in s for s in b[key]) < 2)}
    for lang in ("fr", "en"):
        sa, sb = a["speak"][lang], b["speak"][lang]
        common = sorted(set(sa) & set(sb))
        dd = np.array([sa[i] - sb[i] for i in common])
        mean, lo, hi, _, n = boot_mean_ci(dd)
        out[f"speak_test_{lang}"] = {"diff_pts": round(100 * mean, 1), "ci95_pts": [round(100 * lo, 1), round(100 * hi, 1)],
                                     "n": n}
    return out


def verdict(c):
    better = c["v2_ci95_pts"][0] > 0
    inv_better = c["inv"]["cases_better"] >= 6 and c["inv"]["sign_test_p"] < 0.05
    non_inferior = (c["v2_diff_pts"] > -5.5 and c["inv"]["per36_a"] - c["inv"]["per36_b"] <= 1.0
                    and not c["inv"]["new_cases_2_of_3_seeds"]
                    and all(c[f"speak_test_{lang}"]["diff_pts"] > -14 for lang in ("fr", "en")))
    return {"v2_better": better, "inventions_better": inv_better, "non_inferior": non_inferior}


def main():
    ev, labels = Path(sys.argv[1]), sys.argv[2:]
    data = {label: load(ev, label) for label in labels}
    per_case = {c: {label: {"v2_mean": round(float(np.nanmean(d["v2"][:, i])), 3),
                            "inv_seeds": sum(c in s for s in d["inv"]),
                            "inv_ground_seeds": sum(c in s for s in d["ground"])}
                    for label, d in data.items()} for i, c in enumerate(CASES)}
    cand = labels[0]
    pairs = {f"{cand} vs {ref}": {**compare(data[cand], data[ref])} for ref in labels[1:]}
    for c in pairs.values():
        c["verdict"] = verdict(c)
    print(json.dumps({"contested_cases": CONTESTED, "pairs": pairs, "per_case": per_case,
                      "speak_test_per_case": {label: d["speak"] for label, d in data.items()}},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
