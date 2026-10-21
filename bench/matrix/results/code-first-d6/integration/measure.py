"""D6 intégration : note de production avant/après, lots A à D fusionnés (RIGUEUR: brouillon).

Depuis le dossier bench/matrix/v3/tools de l'arbre à mesurer (v3lib y prend src/) :

    python3 <ce fichier> dump <dev|test> <out.json> <runs/> <generic.json>
    python3 <ce fichier> compare <dev|test> <avant.json> <après.json> [--said]

Runs : <runs>/<modèle>-<split>-b<graine>.json, modèles g3b (harnais générique L5) et v10 (harnais
affiné L5, harness/<split>.json). `compare` donne la note par graine, la part dite en code, l'écart
apparié par cas (bootstrap de power_v3, moyenne des 3 graines) et, sur dev avec --said, les phrases
du code changées. Aucune réponse de modèle n'est affichée ; sur test, aucune phrase n'est affichée.
"""

import json
import sys

import numpy as np

sys.path.insert(0, ".")
import v3lib  # noqa: F401,E402
import power_v3  # noqa: E402
import score_production as sp  # noqa: E402
import score_v3  # noqa: E402

SEEDS = (7, 42, 123)
MODELS = ("g3b", "v10")


def dump(split, out, runs_dir, generic):
    cases = score_v3.load_cases(split)
    h_gen = {h["id"]: h for h in json.load(open(generic))}
    h_ft = score_v3.load_harness(split)
    res = {}
    for m in MODELS:
        for s in SEEDS:
            r = sp.score_run(cases, f"{runs_dir}/{m}-{split}-b{s}.json", h_gen if m == "g3b" else h_ft)
            res[f"{m}-b{s}"] = {k: r[k] for k in ("quality", "code_share", "code_quality", "model_quality", "per_case")}
            print(m, s, r["quality"], r["code_share"])
    json.dump(res, open(out, "w"), ensure_ascii=False)


def compare(split, before_path, after_path, *flags):
    before, after = json.load(open(before_path)), json.load(open(after_path))
    rng = np.random.default_rng(20261001)
    n_cases = len({score_v3.parse_row_id(r)[0] for r in before["g3b-b7"]["per_case"]})
    for m in MODELS:
        keys = [f"{m}-b{s}" for s in SEEDS]
        per_b = {rid: [before[k]["per_case"][rid]["score"] for k in keys] for rid in before[keys[0]]["per_case"]}
        per_a = {rid: [after[k]["per_case"][rid]["score"] for k in keys] for rid in per_b}
        c = power_v3.compare(power_v3.case_means(per_a), power_v3.case_means(per_b), {split: n_cases}, rng, 100)
        better = sum(np.mean(per_a[r]) > np.mean(per_b[r]) + 1e-9 for r in per_b)
        worse = sum(np.mean(per_a[r]) < np.mean(per_b[r]) - 1e-9 for r in per_b)
        print(f"{m}: avant {[before[k]['quality'] for k in keys]} après {[after[k]['quality'] for k in keys]}"
              f" | part en code {before[keys[0]]['code_share']} -> {after[keys[0]]['code_share']}"
              f" | note des lignes en code {before[keys[0]]['code_quality']} -> {after[keys[0]]['code_quality']}"
              f" | écart apparié {c['diff']:+.2f} IC95 {c['ci95']} sur {c['n_cases']} cas, p signe {c['sign_test_p']}"
              f" | évaluations mieux {better}, moins bien {worse}")
    first = before["g3b-b7"]["per_case"]
    changed = [rid for rid in first if first[rid]["said"] != after["g3b-b7"]["per_case"][rid]["said"]
               and after["g3b-b7"]["per_case"][rid]["source"] == "code"]
    print("évaluations dont la phrase de code change :", len(changed))
    if "--said" in flags and split == "dev":
        for rid in sorted(changed):
            print(f"{rid}\t{after['g3b-b7']['per_case'][rid]['said']}")


if __name__ == "__main__":
    {"dump": dump, "compare": compare}[sys.argv[1]](*sys.argv[2:])
