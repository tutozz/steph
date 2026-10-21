#!/usr/bin/env python3
"""G5 évaluation : variantes Granite 4.0 H 350M contre v1.0, banc v3 aligné L5 (harnais affiné, dev ou test).

    PYTHONPATH=<v3/tools>:<round-3/r3t2p3>:<finetune> python3 g5_eval.py <dev|test> <runs/> <verdicts/> <style/> <harness/> <out.json>

Copie de g3b_eval.py (G3b) : seuls changent le split (dev pour le choix, test une fois), la liste des
modèles (lue dans les noms de runs <modèle>-<split>-b<graine>.json) et les paires (chaque modèle contre
v1.0, et les variantes entre elles). Même méthode : bootstrap apparié par cas, 10 000 tirages, graine
20260928 ; inventions sur les seules graines jugées pour les deux modèles ; mauvaise langue par lang_v3.

SPDX-License-Identifier: MIT
"""

import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import power_v3
import score_production
import score_v3
from lang_v3 import classify
from qa_corpus import is_abstention

SEEDS = (7, 42, 123)
SPLIT = sys.argv[1]
SIZES = {"dev": 429, "test": 654}


def files(d, m, seeds=SEEDS):
    return [str(p) for s in seeds if (p := Path(d) / f"{m}-{SPLIT}-b{s}.json").exists()]


def rows_of(f):
    return {r["id"]: r.get("out") for r in json.load(open(f))["rows"]}


def per_eval(fs, fn):
    out = defaultdict(list)
    for f in fs:
        for rid, out_ in rows_of(f).items():
            v = fn(rid, out_)
            if v is not None:
                out[rid].append(v)
    return out


def compare(a, b, rng):
    return power_v3.compare(a, b, {SPLIT: SIZES[SPLIT]}, rng, 100)


def ci_s(c):
    return {k: c[k] for k in ("n_cases", "a", "b", "diff", "ci95", "sign_test_p")}


def wrong_lang_fn(reach):
    def fn(rid, out):
        if rid not in reach:
            return None
        got = classify(out or "")
        return float(got is not None and got != rid.rsplit("@", 1)[1])
    return fn


def compare_evals(a, b, rng):
    """Écart apparié par évaluation (unité de r2_lang.py)."""
    ids = sorted(set(a) & set(b))
    d = np.array([np.mean(a[i]) - np.mean(b[i]) for i in ids])
    lo, hi = power_v3.boot_ci(d, rng)
    return {"n": len(ids), "a": round(100 * float(np.mean([np.mean(a[i]) for i in ids])), 2),
            "b": round(100 * float(np.mean([np.mean(b[i]) for i in ids])), 2),
            "diff": round(100 * float(d.mean()), 2), "ci95": [round(100 * lo, 2), round(100 * hi, 2)]}


def boot_net(vals, rng, n=10_000):
    v = np.array(vals, dtype=float)
    idx = rng.integers(0, len(v), size=(n, len(v)))
    bs = v[idx].mean(axis=1)
    return round(100 * float(v.mean()), 1), [round(100 * float(np.percentile(bs, 2.5)), 1),
                                             round(100 * float(np.percentile(bs, 97.5)), 1)]


def style(path, rng):
    rs = [r for r in json.load(open(path)) if not r.get("error")]
    out = {"n": len(rs), "errors": len(json.load(open(path))) - len(rs),
           "unstable": sum(bool(r["unstable"]["global"]) for r in rs)}
    for lang in ("all", "fr", "en"):
        sub = [r for r in rs if lang == "all" or r["lang"] == lang]
        vals = [{"x": 1, "y": -1, "=": 0}[r["final"]["global"]] for r in sub]
        net, ci = boot_net(vals, rng) if vals else (None, None)
        out[lang] = {"n": len(sub), "x": vals.count(1), "y": vals.count(-1), "=": vals.count(0), "net_x": net, "ci95": ci}
    return out


def production(m, fs, cases, hd):
    harness = {h["id"]: h for h in json.load(open(Path(hd) / f"{SPLIT}.json"))}
    res = [score_production.score_run(cases, f, harness) for f in fs]
    per = defaultdict(list)
    for r in res:
        for rid, p in r["per_case"].items():
            per[rid].append(p["score"])
    return res, per


def main():
    rd, vd, sd, hd, outp = sys.argv[2:7]
    rng = np.random.default_rng(20260928)
    cases = score_v3.load_cases(SPLIT)
    harness = score_v3.load_harness(SPLIT)
    models = sorted({p.name.rsplit(f"-{SPLIT}-b", 1)[0] for p in Path(rd).glob(f"*-{SPLIT}-b*.json")})
    cands = [m for m in models if m != "v10"]
    pairs = [(m, "v10") for m in cands] + list(itertools.combinations(cands, 2))
    reach = {rid for rid, h in harness.items() if h["reaches_model"]}
    qa_ids = {c for c, x in cases.items() if x["task"] == "qa"}
    present = {c for c in qa_ids if cases[c].get("answer_in_history", True)}
    fr_out_en = {f"{c}@en" for c, x in cases.items() if x["output_lang"] == "fr"}
    prod = {m: production(m, files(rd, m), cases, hd) for m in models if files(rd, m)}
    # only this session's verdict files: cache copies from R2 carry the same model_file names
    judged, verd = defaultdict(set), []
    for m in models:
        for s in SEEDS:
            p = Path(vd) / f"inv-{m}-{SPLIT}-b{s}.json"
            if p.exists():
                judged[m].add(s)
                verd += json.load(open(p))

    q = {m: power_v3.per_eval_quality(cases, files(rd, m)) for m in models}
    wl = {m: per_eval(files(rd, m), wrong_lang_fn(reach)) for m in models}
    ab = {m: per_eval(files(rd, m), lambda rid, o: float(bool(is_abstention(o or "")))
                      if rid.rsplit("@", 1)[0] in qa_ids else None) for m in models}

    report = {"models": {}, "pairs": {}, "style": {}}
    for m in models:
        fs = files(rd, m)
        if not fs:
            continue
        res = [score_v3.score_file(cases, f) for f in fs]
        rr = [score_v3.score_file(cases, f, only=reach) for f in fs]
        mean = lambda xs: round(float(np.mean(xs)), 1)  # noqa: E731
        qm = power_v3.case_means(q[m])
        inv = [v for v in verd if v["model_file"].startswith(f"{m}-{SPLIT}-b") and v["final"] != "erreur"]
        report["models"][m] = {
            "seeds": len(fs), "missing": sum(r["missing"] for r in res),
            **{k: mean([r[k] for r in res]) for k in ("quality", "fr", "en", "summary", "qa")},
            "quality_by_seed": [r["quality"] for r in res],
            "reaches_model": mean([r["quality"] for r in rr]),
            "qa_present": round(100 * float(np.mean([qm[c] for c in present])), 1),
            "qa_absent": round(100 * float(np.mean([qm[c] for c in qa_ids - present])), 1),
            "abst_present": [int(sum(ab[m][r][i] for r in ab[m] if r.rsplit("@", 1)[0] in present)) for i in range(len(fs))],
            "abst_absent": [int(sum(ab[m][r][i] for r in ab[m] if r.rsplit("@", 1)[0] not in present)) for i in range(len(fs))],
            "wrong_lang_pct": {lang: round(100 * float(np.mean([np.mean(v) for r, v in wl[m].items() if r.endswith(lang)])), 2)
                               for lang in ("@fr", "@en")},
            "wrong_lang_en_fr_output_pct": round(100 * float(np.mean([np.mean(v) for r, v in wl[m].items() if r in fr_out_en])), 2),
            "wrong_lang_en_fr_output_n": sum(r in fr_out_en for r in wl[m]),
            "production": {"quality": mean([r["quality"] for r in prod[m][0]]),
                           "by_seed": [r["quality"] for r in prod[m][0]],
                           "code_share": prod[m][0][0]["code_share"], "fallback": [r["fallback"] for r in prod[m][0]],
                           "fr": mean([r["fr"] for r in prod[m][0]]), "en": mean([r["en"] for r in prod[m][0]])},
            "inventions": {"seeds": sorted(judged[m]), "n": len(inv),
                           "pct": round(100 * sum(v["final"] == "invention" for v in inv) / len(inv), 1) if inv else None,
                           "douteux_pct": round(100 * sum(v["final"] == "douteux" for v in inv) / len(inv), 1) if inv else None}}

    for a, b in pairs:
        if a not in report["models"] or b not in report["models"]:
            continue
        pr = {"quality": ci_s(compare(power_v3.case_means(q[a]), power_v3.case_means(q[b]), rng)),
              "reaches_model": ci_s(compare(power_v3.case_means(q[a], reach), power_v3.case_means(q[b], reach), rng))}
        for name, keep in (("summary", {r for r in q[a] if r.rsplit("@", 1)[0] not in qa_ids}),
                           ("qa", {r for r in q[a] if r.rsplit("@", 1)[0] in qa_ids}),
                           ("qa_present", {r for r in q[a] if r.rsplit("@", 1)[0] in present}),
                           ("qa_absent", {r for r in q[a] if r.rsplit("@", 1)[0] in qa_ids - present}),
                           ("fr", {r for r in q[a] if r.endswith("@fr")}), ("en", {r for r in q[a] if r.endswith("@en")})):
            pr[name] = ci_s(compare(power_v3.case_means(q[a], keep), power_v3.case_means(q[b], keep), rng))
        for lang in ("@fr", "@en"):
            pr["wrong_lang" + lang.replace("@", "_")] = compare_evals(
                {r: v for r, v in wl[a].items() if r.endswith(lang)}, {r: v for r, v in wl[b].items() if r.endswith(lang)}, rng)
        pr["wrong_lang_en_fr_output"] = compare_evals(
            {r: v for r, v in wl[a].items() if r in fr_out_en}, {r: v for r, v in wl[b].items() if r in fr_out_en}, rng)
        pr["production"] = ci_s(compare(power_v3.case_means(prod[a][1]), power_v3.case_means(prod[b][1]), rng))
        common = sorted(judged[a] & judged[b])
        if common:
            ia = power_v3.per_eval_invention(verd, files(rd, a, common))
            ib = power_v3.per_eval_invention(verd, files(rd, b, common))
            pr["inventions"] = {"seeds": common, **ci_s(compare(power_v3.case_means(ia), power_v3.case_means(ib), rng))}
        report["pairs"][f"{a} - {b}"] = pr

    for p in sorted(Path(sd).glob("style-*-vs-*.json")):
        report["style"][p.stem.removeprefix("style-")] = style(p, rng)
    Path(outp).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report["models"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
