#!/usr/bin/env python3
"""L5 : note composite de production, avec et sans bloc de faits, split dev, 3 graines.

    python3 analyze_l5.py <runs_dir> <harness_dir> > l5-dev.json

runs_dir : <model>-<base|facts>-dev-b<seed>.json (bench_run.py) pour model gemma et r1.
harness_dir : dev.json, dev.facts.json (profil affiné), dev.generic.json, dev.generic.facts.json.
Écart apparié par cas (moyenne des graines puis des deux langues), bootstrap de power_v3.
« Interdit touché » : réponse entendue qui touche un interdit global ou du cas, sur les lignes
envoyées au modèle ; indicateur déterministe d'invention, pas le juge A7.

SPDX-License-Identifier: MIT
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "v3" / "tools"))
import power_v3  # noqa: E402
import score_production  # noqa: E402
import score_v3  # noqa: E402

SEEDS = (7, 42, 123)
HARNESS = {("gemma", "base"): "dev.generic.json", ("gemma", "facts"): "dev.generic.facts.json",
           ("r1", "base"): "dev.json", ("r1", "facts"): "dev.facts.json"}


def forbidden(case, lang, text):
    t = score_v3.plain(score_v3.clean(text))
    views = (t, score_v3.number_view(t), score_v3.absence_view(score_v3.number_view(t)))
    hit = lambda ps: any(score_v3.any_match(ps, v) for v in views)  # noqa: E731
    return hit(score_v3.GLOBAL_NEVER) or any(hit(f[lang]) for f in case["facts"]["never"])


def main():
    runs, hdir = Path(sys.argv[1]), Path(sys.argv[2])
    cases = score_v3.load_cases("dev")
    facts_rows = {h["id"] for h in json.load(open(hdir / "dev.generic.facts.json"))
                  if h["kind"] == "summary" and h["reaches_model"]
                  and any(k in h["messages"][1]["content"] for k in ("Faits extraits en code :", "Facts extracted by code:"))}
    report, per_row = {}, {}
    for (model, variant), hname in HARNESS.items():
        harness = {h["id"]: h for h in json.load(open(hdir / hname))}
        seeds = {}
        rows = defaultdict(dict)
        for sd in SEEDS:
            path = runs / f"{model}-{variant}-dev-b{sd}.json"
            if not path.exists():
                continue
            res = score_production.score_run(cases, path, harness)
            per = res.pop("per_case")
            model_rows = {rid: p for rid, p in per.items() if p["source"] != "code"}
            touched = [p["score"] for rid, p in per.items() if rid in facts_rows]
            bad = [forbidden(cases[score_v3.parse_row_id(rid)[0]], score_v3.parse_row_id(rid)[1], p["said"])
                   for rid, p in model_rows.items()]
            seeds[sd] = {"quality": res["quality"], "model_quality": res["model_quality"],
                         "fallback": res["fallback"], "facts_rows_quality": score_v3.mean_pct(touched),
                         "facts_rows": len(touched), "forbidden_pct": round(100 * sum(bad) / len(bad), 1),
                         "fr": res["fr"], "en": res["en"], "by_family": res["by_family"]}
            for rid, p in per.items():
                rows[rid][sd] = p["score"]
        report[f"{model}-{variant}"] = seeds
        per_row[(model, variant)] = rows
    rng = np.random.default_rng(20260929)
    sizes = {"dev": 429}
    for model in ("gemma", "r1"):
        fa, fb = per_row[(model, "facts")], per_row[(model, "base")]
        seeds = [sd for sd in SEEDS if any(sd in v for v in fa.values()) and any(sd in v for v in fb.values())]
        report[f"{model}-paired-seeds"] = seeds
        a = {rid: [v[sd] for sd in seeds] for rid, v in fa.items()}
        b = {rid: [v[sd] for sd in seeds] for rid, v in fb.items()}
        common = set(a) & set(b)
        report[f"{model}-diff"] = power_v3.compare(power_v3.case_means(a, common), power_v3.case_means(b, common),
                                                   sizes, rng, 100)
        touched = common & facts_rows
        report[f"{model}-diff-facts-rows"] = power_v3.compare(power_v3.case_means(a, touched),
                                                              power_v3.case_means(b, touched), {"rows": len(touched)},
                                                              rng, 100)
        # lignes sans bloc : entrée identique, tout écart ici est du bruit de génération
        other = common - facts_rows
        report[f"{model}-other-rows-discordant"] = sum(a[r] != b[r] for r in other)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
