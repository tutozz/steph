#!/usr/bin/env python3
"""G4 : variantes quantifiées de Gemma 4 E2B (brut QAT) contre le Q4_0 officiel, banc v3 test.

    PYTHONPATH=<v3/tools>:<round-3/r3t2p3>:<finetune>:<g3> python3 g4_eval.py <runs/> <verdicts/> <out.json> <modèle>...

Runs <runs>/<modèle>-test-b<graine>.json ; verdicts A7 <verdicts>/inv-<modèle>-test-b<graine>.json. Référence :
gemma-raw (Q4_0 officiel, runs G3). Chaque écart est apparié par cas sur les graines communes aux deux modèles,
méthode de g3_eval.py (power_v3, bootstrap 10 000 tirages, graine 20260928).

SPDX-License-Identifier: MIT
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import power_v3
import score_v3
from g3_eval import ci_s, compare, compare_evals, per_eval, wrong_lang_fn

SEEDS = (7, 42, 123)
REF = "gemma-raw"


def seeds_of(d, m):
    return {s for s in SEEDS if (Path(d) / f"{m}-test-b{s}.json").exists()}


def files(d, m, seeds):
    return [str(Path(d) / f"{m}-test-b{s}.json") for s in sorted(seeds)]


def verdicts(vd, m, seeds):
    out = []
    for s in seeds:
        p = Path(vd) / f"inv-{m}-test-b{s}.json"
        if p.exists():
            out += [v for v in json.load(open(p)) if v["final"] != "erreur"]
    return out


def main():
    rd, vd, outp, *models = sys.argv[1:]
    rng = np.random.default_rng(20260928)
    cases = score_v3.load_cases("test")
    harness = score_v3.load_harness("test")
    reach = {rid for rid, h in harness.items() if h["reaches_model"]}
    qa_ids = {c for c, x in cases.items() if x["task"] == "qa"}
    report = {"models": {}, "vs_ref": {}}
    for m in [REF, *models]:
        sd = seeds_of(rd, m)
        judged = {s for s in sd if (Path(vd) / f"inv-{m}-test-b{s}.json").exists()}
        fs = files(rd, m, sd)
        res = [score_v3.score_file(cases, f) for f in fs]
        rr = [score_v3.score_file(cases, f, only=reach) for f in fs]
        inv = verdicts(vd, m, judged)
        wl = per_eval(fs, wrong_lang_fn(reach))
        mean = lambda xs: round(float(np.mean(xs)), 2)  # noqa: E731
        report["models"][m] = {
            "seeds": sorted(sd), "judged": sorted(judged), "missing": sum(r["missing"] for r in res),
            **{k: mean([r[k] for r in res]) for k in ("quality", "fr", "en", "summary", "qa")},
            "quality_by_seed": [r["quality"] for r in res], "reaches_model": mean([r["quality"] for r in rr]),
            "inventions_pct": round(100 * sum(v["final"] == "invention" for v in inv) / len(inv), 2) if inv else None,
            "douteux_pct": round(100 * sum(v["final"] == "douteux" for v in inv) / len(inv), 2) if inv else None,
            "n_judged": len(inv),
            "wrong_lang_pct": {lg: round(100 * float(np.mean([np.mean(v) for r, v in wl.items() if r.endswith(lg)])), 2)
                               for lg in ("@fr", "@en")}}
        if m == REF:
            continue
        common = sorted(sd & seeds_of(rd, REF))
        qa = power_v3.per_eval_quality(cases, files(rd, m, common))
        qb = power_v3.per_eval_quality(cases, files(rd, REF, common))
        pr = {"seeds": common,
              "quality": ci_s(compare(power_v3.case_means(qa), power_v3.case_means(qb), rng)),
              "reaches_model": ci_s(compare(power_v3.case_means(qa, reach), power_v3.case_means(qb, reach), rng))}
        for name, keep in (("summary", {r for r in qa if r.rsplit("@", 1)[0] not in qa_ids}),
                           ("qa", {r for r in qa if r.rsplit("@", 1)[0] in qa_ids})):
            pr[name] = ci_s(compare(power_v3.case_means(qa, keep), power_v3.case_means(qb, keep), rng))
        wa = per_eval(files(rd, m, common), wrong_lang_fn(reach))
        wb = per_eval(files(rd, REF, common), wrong_lang_fn(reach))
        for lg in ("@fr", "@en"):
            pr["wrong_lang" + lg.replace("@", "_")] = compare_evals(
                {r: v for r, v in wa.items() if r.endswith(lg)}, {r: v for r, v in wb.items() if r.endswith(lg)}, rng)
        cj = sorted(set(common) & set(report["models"][m]["judged"]) & set(report["models"][REF]["judged"]))
        if cj:
            verd = verdicts(vd, m, cj) + verdicts(vd, REF, cj)
            ia = power_v3.per_eval_invention(verd, files(rd, m, cj))
            ib = power_v3.per_eval_invention(verd, files(rd, REF, cj))
            pr["inventions"] = {"seeds": cj, **ci_s(compare(power_v3.case_means(ia), power_v3.case_means(ib), rng))}
        report["vs_ref"][m] = pr
    Path(outp).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    for m, r in report["models"].items():
        p = report["vs_ref"].get(m, {})
        print(f"{m:22s} seeds {r['seeds']} q {r['quality']} inv {r['inventions_pct']} "
              f"dq {p.get('quality', {}).get('diff')} {p.get('quality', {}).get('ci95')} "
              f"dinv {p.get('inventions', {}).get('diff')} {p.get('inventions', {}).get('ci95')}")


if __name__ == "__main__":
    main()
