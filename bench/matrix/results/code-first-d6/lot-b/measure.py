"""D6 lot B : note de production dev par graine, avec le code au HEAD (RIGUEUR: brouillon).

    cd bench/matrix/v3/tools
    python3 ../../results/code-first-d6/lot-b/measure.py dump <out.json> <runs_v10_dir> <dev.generic.json>
    python3 ../../results/code-first-d6/lot-b/measure.py compare <avant.json> <après.json>

`dump` rejoue score_production.py sur v1.0 (runs v10-dev-b*.json de la 3080, harnais affiné L5)
et Gemma brut L5 (results/aids-input/runs/gemma-facts-dev-b*.json, harnais générique L5) ; un
éventuel g3b-dev-b*.json posé dans <runs_v10_dir> est ajouté. `compare` donne l'écart par règle
et les phrases de code changées ; il n'affiche jamais une réponse de modèle.
"""

import collections
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
import v3lib  # noqa: F401,E402
import score_production as sp  # noqa: E402
import score_v3  # noqa: E402
from steph import digest as dg  # noqa: E402

GEMMA = Path(__file__).resolve().parents[2] / "aids-input" / "runs"
RULES = [dg._verbose_count, dg._checksum, dg._diff_brief, dg._wc_total, dg._rsync_summary, dg._script_error,
         dg._grep_count]


def dump(out, runs_dir, generic):
    cases = score_v3.load_cases("dev")
    h_ft = score_v3.load_harness("dev")
    h_gen = {h["id"]: h for h in json.load(open(generic))}
    runs = {f"v10-b{s}": (f"{runs_dir}/v10-dev-b{s}.json", h_ft) for s in (7, 42, 123)}
    runs.update({f"gemma-b{s}": (f"{GEMMA}/gemma-facts-dev-b{s}.json", h_gen) for s in (7, 42, 123)})
    for p in sorted(glob.glob(f"{runs_dir}/g3b-dev-b*.json")):
        runs["g3b-" + p.rsplit("-", 1)[1][:-5]] = (p, h_gen)
    res = {}
    for name, (path, h) in runs.items():
        r = sp.score_run(cases, path, h)
        res[name] = {"quality": r["quality"], "code_share": r["code_share"], "per_case": r["per_case"]}
        print(name, r["quality"], r["code_share"])
    json.dump(res, open(out, "w"), ensure_ascii=False)


def rule_of(case, lang):
    first, args = dg._program(case["cmd"].split("|")[0])
    for f in RULES:
        if f(first, args, case["cmd"], case["exit"] not in (0, None), case["output_raw"], lang):
            return f.__name__
    return "other"


def compare(before_path, after_path):
    before, after = json.load(open(before_path)), json.load(open(after_path))
    cases = score_v3.load_cases("dev")
    models = sorted({k.split("-b")[0] for k in before})
    first = next(iter(before))
    n = len(before[first]["per_case"])
    agg, rows = collections.defaultdict(collections.Counter), []
    for rid in before[first]["per_case"]:
        b, a = before[first]["per_case"][rid], after[first]["per_case"][rid]
        if b["said"] == a["said"]:
            continue
        cid, lang = score_v3.parse_row_id(rid)
        rule = rule_of(cases[cid], lang)
        agg[rule]["rows"] += 1
        deltas = {}
        for m in models:
            seeds = [k for k in before if k.startswith(m + "-b")]
            d = sum(after[k]["per_case"][rid]["score"] - before[k]["per_case"][rid]["score"] for k in seeds) / len(seeds)
            deltas[m] = d
            agg[rule][m] += d
            agg[rule][m + "+"] += d > 1e-9
            agg[rule][m + "-"] += d < -1e-9
        said = a["said"] if a["source"] == "code" else "<modèle>"
        rows.append(f"{rule:14} {rid:34} " + " ".join(f"{m}{deltas[m]:+.2f}" for m in models)
                    + f" note={a['score']:.2f} | {said}")
    for rule, c in sorted(agg.items()):
        print(f"{rule:16} {c['rows']:3} évaluations", " ".join(
            f"{m} {100 * c[m] / n:+.2f} ({c[m + '+']}+/{c[m + '-']}-)" for m in models))
    for m in models:
        seeds = [k for k in before if k.startswith(m + "-b")]
        print(m, "avant", [before[k]["quality"] for k in seeds], "après", [after[k]["quality"] for k in seeds],
              "part en code", before[seeds[0]]["code_share"], "->", after[seeds[0]]["code_share"])
    print("\n".join(sorted(rows)))


if __name__ == "__main__":
    {"dump": dump, "compare": compare}[sys.argv[1]](*sys.argv[2:])
