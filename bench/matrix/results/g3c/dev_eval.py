#!/usr/bin/env python3
"""G3c, contrôle rapide sur DEV (pas de décision) : chaque modèle contre G3b, banc v3 dev générique aligné L5, une graine
(42). Mesures et méthode de g3b_eval.py ramenées au DEV : qualité (score_v3), note de production (score_production, harnais
du run), questions à réponse présente, inventions A7 (réponses reaches_model), mauvaise langue (lang_v3), écarts appariés
par cas, bootstrap 10 000 tirages, graine 20260928.

    PYTHONPATH=<v3/tools>:<r2c1>:<finetune>:<src> python3 dev_eval.py <runs/> <verdicts/> <dev.generic.json> <out.json> g3b <modèle>...

SPDX-License-Identifier: MIT
"""

import json
import sys
from pathlib import Path

import numpy as np

import power_v3
import score_production
import score_v3
from lang_v3 import classify

SIZES = {"dev": 429}


def run(d, m):
    return str(Path(d) / f"{m}-dev-b42.json")


def ci(c):
    return {k: c[k] for k in ("n_cases", "a", "b", "diff", "ci95", "sign_test_p")}


def main():
    rd, vd, hp, outp, ref, *models = sys.argv[1:]
    rng = np.random.default_rng(20260928)
    cases = score_v3.load_cases("dev")
    reach = {rid for rid, h in score_v3.load_harness("dev").items() if h["reaches_model"]}
    harness = {h["id"]: h for h in json.load(open(hp))}
    qa_ids = {c for c, x in cases.items() if x["task"] == "qa"}
    present = {c for c in qa_ids if cases[c].get("answer_in_history", True)}
    fr_out_en = {f"{c}@en" for c, x in cases.items() if x["output_lang"] == "fr"}
    verd = [v for m in [ref, *models] for v in json.load(open(Path(vd) / f"inv-{m}-dev-b42.json"))]

    per = {}
    for m in [ref, *models]:
        f = run(rd, m)
        rows = {r["id"]: r.get("out") or "" for r in json.load(open(f))["rows"]}
        wl = {rid: float((g := classify(o)) is not None and g != rid.rsplit("@", 1)[1]) for rid, o in rows.items() if rid in reach}
        pr = score_production.score_run(cases, f, harness)
        per[m] = {"q": power_v3.per_eval_quality(cases, [f]), "wl": wl,
                  "prod": {rid: [p["score"] for p in [x]] for rid, x in pr["per_case"].items()},
                  "inv": power_v3.per_eval_invention(verd, [f]), "res": score_v3.score_file(cases, f), "pr": pr}

    report = {"models": {}, "vs_" + ref: {}}
    for m, p in per.items():
        inv = [v for v in verd if v["model_file"] == Path(run(rd, m)).name and v["final"] != "erreur"]
        qm = power_v3.case_means(p["q"])
        report["models"][m] = {
            **{k: p["res"][k] for k in ("quality", "fr", "en", "summary", "qa", "missing")},
            "production": p["pr"]["quality"], "production_model": p["pr"]["model_quality"],
            "qa_present": round(100 * float(np.mean([qm[c] for c in present])), 1),
            "inventions_pct": round(100 * sum(v["final"] == "invention" for v in inv) / len(inv), 1),
            "douteux_pct": round(100 * sum(v["final"] == "douteux" for v in inv) / len(inv), 1), "judged": len(inv),
            "wrong_lang_fr_pct": round(100 * float(np.mean([v for r, v in p["wl"].items() if r.endswith("@fr")])), 2),
            "wrong_lang_en_pct": round(100 * float(np.mean([v for r, v in p["wl"].items() if r.endswith("@en")])), 2),
            "wrong_lang_en_fr_output_pct": round(100 * float(np.mean([v for r, v in p["wl"].items() if r in fr_out_en])), 2)}
    a_ = per[ref]
    for m in models:
        b_ = per[m]

        def cmp(key, keep=None, scale=100):
            return ci(power_v3.compare(power_v3.case_means(b_[key], keep), power_v3.case_means(a_[key], keep),
                                       SIZES, rng, scale))
        report["vs_" + ref][m] = {
            "quality": cmp("q"), "production": cmp("prod"), "inventions": cmp("inv"),
            "qa_present": cmp("q", {r for r in b_["q"] if r.rsplit("@", 1)[0] in present}),
            "wrong_lang_en": ci(power_v3.compare({r: v for r, v in b_["wl"].items() if r.endswith("@en")},
                                                 {r: v for r, v in a_["wl"].items() if r.endswith("@en")}, SIZES, rng, 100))}
    Path(outp).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
