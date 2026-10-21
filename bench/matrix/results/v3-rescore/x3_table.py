#!/usr/bin/env python3
"""X3 : tableau unique du rescore v3 (qualité dev et test, reaches_model, questions, bonne langue,
inventions au juge A7, comparaison appariée contre R1).

    PYTHONPATH=<bench/matrix/v3/tools>:<bench/matrix/finetune/pref> python3 x3_table.py <models.json> <runs/> <judge/> <out.json>

models.json : [{"name", "profile", "kind", "size_mb", "i5_p90", "i5_src"}, ...]. Runs :
<runs>/<name>-<dev|test>-b<graine>.json ; verdicts : <judge>/inv-<name>-<split>-b<graine>.json (réponses reaches_model seulement, judge_x3.py).
Score : score_v3 et power_v3 du banc (même règle, bootstrap apparié par cas, 10 000 tirages).

SPDX-License-Identifier: MIT
"""

import json
import re
import sys
from pathlib import Path

import numpy as np

import power_v3
import score_v3
from lang_rate import cosine, profiles, trigrams

SEEDS = (7, 42, 123)
REF = "r1-v1.0"


def runs(d, name, split):
    return [str(p) for sd in SEEDS if (p := Path(d) / f"{name}-{split}-b{sd}.json").exists()]


def verdicts(d, name, split):
    out = []
    for sd in SEEDS:
        p = Path(d) / f"inv-{name}-{split}-b{sd}.json"
        if p.exists():
            out += [v for v in json.load(open(p))]
    return out


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(float(np.mean(xs)), 1) if xs else None


def quality(cases, harness, files):
    reach = {rid for rid, h in harness.items() if h["reaches_model"]}
    res = [score_v3.score_file(cases, f) for f in files]
    rr = [score_v3.score_file(cases, f, only=reach) for f in files]
    return {k: mean([r[k] for r in res]) for k in ("quality", "fr", "en", "summary", "qa")} | {
        "reaches_model": mean([r["quality"] for r in rr]), "seeds": len(files),
        "missing": sum(r["missing"] for r in res),
        "quality_by_seed": [r["quality"] for r in res]}


WORDS = re.compile(r"\b[^\W\d_]{3,}\b")  # réponse jugeable : 4 mots de 3 lettres ou plus, sinon neutre


def fr_or_en(text, profs):
    """Classe binaire FR contre EN (profils de lang_rate) : la seule confusion qui compte ici ;
    à six langues, les réponses techniques courtes partent souvent vers de, es ou pt."""
    g = trigrams(text)
    return max(("fr", "en"), key=lambda lang: cosine(g, profs[lang]))


def right_lang(files, profs):
    out = {}
    for lang in ("fr", "en"):
        ans = [r["out"] for f in files for r in json.load(open(f))["rows"]
               if r["id"].endswith("@" + lang) and len(WORDS.findall(r.get("out") or "")) >= 4]
        out[lang] = round(100 * sum(fr_or_en(a, profs) == lang for a in ans) / len(ans), 1) if ans else None
    return out


def inventions(vs, files):
    names = {Path(f).name for f in files}
    rs = [v for v in vs if v["model_file"] in names and v["final"] != "erreur"]
    if not rs:
        return None
    by_lang = {lang: [v for v in rs if v["id"].endswith("@" + lang)] for lang in ("fr", "en")}
    return {"n": len(rs), "seeds": len({v["model_file"] for v in rs}),
            "pct": round(100 * sum(v["final"] == "invention" for v in rs) / len(rs), 1),
            "douteux_pct": round(100 * sum(v["final"] == "douteux" for v in rs) / len(rs), 1),
            "fr_pct": round(100 * sum(v["final"] == "invention" for v in by_lang["fr"]) / max(1, len(by_lang["fr"])), 1),
            "en_pct": round(100 * sum(v["final"] == "invention" for v in by_lang["en"]) / max(1, len(by_lang["en"])), 1),
            "erreur": sum(v["model_file"] in names and v["final"] == "erreur" for v in vs)}


def paired(cases, harness, a_files, b_files, va, vb, rng):
    reach = {rid for rid, h in harness.items() if h["reaches_model"]}
    sizes = {"n": len(cases)}
    qa, qb = power_v3.per_eval_quality(cases, a_files), power_v3.per_eval_quality(cases, b_files)
    out = {"quality": power_v3.compare(power_v3.case_means(qa), power_v3.case_means(qb), sizes, rng, 100),
           "reaches_model": power_v3.compare(power_v3.case_means(qa, reach), power_v3.case_means(qb, reach),
                                             sizes, rng, 100)}
    ia, ib = power_v3.per_eval_invention(va, a_files), power_v3.per_eval_invention(vb, b_files)
    if ia and ib:
        out["inventions"] = power_v3.compare(power_v3.case_means(ia), power_v3.case_means(ib), sizes, rng, 100)
    return out


def fmt(x, nd=1):
    return "-" if x is None else f"{x:.{nd}f}".replace(".", ",")


def ci(c):
    return f"{fmt(c['diff'], 2)} [{fmt(c['ci95'][0], 2)} ; {fmt(c['ci95'][1], 2)}]"


def markdown(table):
    """Tableau unique, trié par qualité test ; dev à côté pour contrôle."""
    dev = {r["name"]: r for r in table if r["split"] == "dev"}
    test = sorted((r for r in table if r["split"] == "test"), key=lambda r: -(r["quality"] or 0))
    head = ("| Rang | Modèle | Type | Qualité test | Écart à R1, IC 95 % | reaches_model | Questions | FR / EN "
            "| Bonne langue FR / EN | Inventions (réponses jugées) | Qualité dev | Graines | Mo | p90 i5 (s) |")
    lines = [head, "|" + "---|" * 14]
    for i, r in enumerate(test, 1):
        v = r.get("vs_r1", {})
        inv = r["inventions"]
        inv_s = f"{fmt(inv['pct'])} % ({inv['n']})" if inv else "non jugé"
        if inv and "inventions" in v:
            inv_s += f", écart {ci(v['inventions'])}"
        d = dev.get(r["name"], {})
        lines.append(" | ".join([
            f"| {i}", r["label"], r["kind"], fmt(r["quality"]), ci(v["quality"]) if "quality" in v else "référence",
            fmt(r["reaches_model"]), fmt(r["qa"]), f"{fmt(r['fr'])} / {fmt(r['en'])}",
            f"{fmt(r['right_lang']['fr'])} / {fmt(r['right_lang']['en'])}", inv_s, fmt(d.get("quality")),
            str(r["seeds"]), fmt(r["size_mb"], 0), fmt(r["i5_p90"], 2) + " |"]))
    return "\n".join(lines) + "\n"


def main():
    models_path, run_dir, judge_dir, out_path = sys.argv[1:5]
    models = json.load(open(models_path))
    profs = profiles()
    rng = np.random.default_rng(20260928)
    table = []
    for split in ("dev", "test"):
        cases, harness = score_v3.load_cases(split), score_v3.load_harness(split)
        ref_files, ref_v = runs(run_dir, REF, split), verdicts(judge_dir, REF, split)
        for m in models:
            files = runs(run_dir, m["name"], split)
            if not files:
                continue
            vs = verdicts(judge_dir, m["name"], split)
            row = {**m, "split": split, **quality(cases, harness, files), "right_lang": right_lang(files, profs),
                   "inventions": inventions(vs, files)}
            if m["name"] != REF and ref_files:
                row["vs_r1"] = paired(cases, harness, files, ref_files, vs, ref_v, rng)
            table.append(row)
            print(split, m["name"], row["quality"], row["qa"], (row["inventions"] or {}).get("pct"), flush=True)
    json.dump(table, open(out_path, "w"), ensure_ascii=False, indent=1)
    Path(out_path).with_suffix(".md").write_text(markdown(table))


if __name__ == "__main__":
    main()
