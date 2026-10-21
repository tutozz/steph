#!/usr/bin/env python3
"""Synthèse de T2 (X1, tour 1, élagage de couches de Granite 4.0 H) : v2 et contrôle, bootstrap apparié par
cas contre K3-a, inventions au juge A7 avec la règle de T5, Steph Speak Bench, proxy de vitesse T4.

    python3 t2_summary.py <dossier de résultats round-1/t2> <sortie.json>

Le dossier contient bench/<modèle>-b<graine>.json, judge/*.json, speak/<modèle>/*.json, t4/*.json,
train/*.json. Ne lance aucun modèle.

SPDX-License-Identifier: MIT
"""

import glob
import json
import statistics as st
import subprocess
import sys
from pathlib import Path

import numpy as np

MATRIX = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MATRIX / "loop"))
from bench_power import CONTESTED_FACTS, CONTESTED_INVENTIONS, boot_mean_ci, sign_test_p, v2_matrix  # noqa: E402

REF = "k3a"
MODELS = ("k3a", "cut4", "cut7", "cut9")
GGUF = {"k3a": "k3-a-dpo", "cut4": "t2-cut4", "cut7": "t2-cut7", "cut9": "t2-cut9"}
SEEDS = ("b7", "b42", "b123")
CONTESTED = CONTESTED_FACTS | CONTESTED_INVENTIONS | {"fx24"}


def compact_scores(root, m):
    cases = MATRIX / "cases_compact_granite200_train.json"
    files = [str(root / "bench" / f"{m}-{s}.json") for s in SEEDS]
    out = subprocess.run([sys.executable, str(MATRIX / "finetune/pref/score_compact.py"), str(cases), *files],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def inventions(root, judge_files):
    per = {}
    for f in judge_files:
        for r in json.load(open(root / "judge" / f)):
            m, seed = r["model_file"][:-5].rsplit("-", 1)
            per.setdefault(m, {}).setdefault(seed, set())
            if r["final"] == "invention":
                per[m][seed].add(r["id"])
    return per


def invention_block(per):
    res = {}
    ref = per[REF]
    for m, seeds in per.items():
        counts = [len(seeds[s]) for s in SEEDS]
        new = {}
        for s in SEEDS:
            for c in seeds[s] - ref[s]:
                if c not in CONTESTED:
                    new[c] = new.get(c, 0) + 1
        gone = {}
        for s in SEEDS:
            for c in ref[s] - seeds[s]:
                gone[c] = gone.get(c, 0) + 1
        pos = sum(len(seeds[s] - ref[s]) for s in SEEDS)
        neg = sum(len(ref[s] - seeds[s]) for s in SEEDS)
        res[m] = {"per_seed": counts, "mean": round(st.mean(counts), 2),
                  "new_uncontested_cases": dict(sorted(new.items())),
                  "new_uncontested_on_2_of_3": sorted(c for c, n in new.items() if n >= 2),
                  "fixed_vs_ref": dict(sorted(gone.items())),
                  "discordant_worse_better": [pos, neg], "sign_p": round(sign_test_p(pos, neg), 4)}
    return res


def speak(root, m):
    out = {}
    for f in sorted(glob.glob(str(root / "speak" / m / "*.json"))):
        d = json.load(open(f))
        key = "_".join(Path(f).stem.split("_")[-2:])
        out[key] = {"score": d["summary"]["score"], "n": d["summary"]["n"]}
    return out


def lang_rates(root, m):
    files = sorted(glob.glob(str(root / "speak" / m / "*.json")))
    out = subprocess.run([sys.executable, str(MATRIX / "finetune/pref/lang_rate.py"), *files],
                         capture_output=True, text=True, check=True).stdout
    return {"_".join(Path(k).stem.split("_")[-2:]): v["right_lang_pct"] for k, v in json.loads(out).items()}


def speed(root, m):
    g = GGUF[m]
    runs = [json.load(open(root / "t4" / f"hsw4-b3-{g}-Q4_K_M-p{p}.json")) for p in (1, 2)]
    lb = {(f"pp{x['n_prompt']}" if x["n_gen"] == 0 else f"tg{x['n_gen']}"): round(x["avg_ts"], 1)
          for x in json.load(open(root / "t4" / f"lb-hsw4-{g}-Q4_K_M.json"))}
    pp = [sum(r["prompt_n"] for r in x["rows"]) / sum(r["prompt_ms"] for r in x["rows"]) * 1000 for x in runs]
    return {"ttft_p90": [x["ttft_p90"] for x in runs], "ttft_median": [x["ttft_median"] for x in runs],
            "ram_peak_mb": [x["ram_peak_mb"] for x in runs], "prefill_tok_s_bench": [round(v, 1) for v in pp],
            "llama_bench": lb, "i5_ttft_p90_predicted_s": round(st.mean(x["ttft_p90"] for x in runs) * 2.51, 2)}


def main():
    root, dest = Path(sys.argv[1]), sys.argv[2]
    mats = {m: v2_matrix([str(root / "bench" / f"{m}-{s}.json") for s in SEEDS]) for m in MODELS}
    judge = sorted(p.name for p in (root / "judge").glob("*.json"))
    raw = {k: inventions(root, [f for f in judge if f.endswith("ground.json") == g]) for k, g in (("raw", False), ("ground", True))}
    summary = {"reference": REF, "models": {}}
    for m in MODELS:
        d = np.nanmean(mats[m], axis=0) - np.nanmean(mats[REF], axis=0)
        mean, lo, hi, sd, n = boot_mean_ci(d * 100)
        sp = speed(root, m)
        base = speed(root, REF)
        summary["models"][m] = {
            "compact": compact_scores(root, m),
            "v2_delta_vs_ref_paired": {"mean": round(mean, 2), "ci95": [round(lo, 2), round(hi, 2)], "n_cases": n},
            "inventions": invention_block(raw["raw"])[m],
            "inventions_ground": invention_block(raw["ground"])[m],
            "speak_steph": speak(root, m), "right_lang_pct": lang_rates(root, m),
            "speed_t4": sp,
            "prefill_gain_pct": round(100 * (st.mean(sp["prefill_tok_s_bench"]) / st.mean(base["prefill_tok_s_bench"]) - 1), 1),
            "pp512_gain_pct": round(100 * (sp["llama_bench"]["pp512"] / base["llama_bench"]["pp512"] - 1), 1),
            "ttft_p90_delta_pct": round(100 * (st.mean(sp["ttft_p90"]) / st.mean(base["ttft_p90"]) - 1), 1),
        }
        tl = root / "train" / f"heal{m[3:]}-train_log.json"
        if tl.exists():
            t = json.load(open(tl))
            summary["models"][m]["heal"] = {k: t[k] for k in ("val_before", "best_val", "best_epoch", "steps", "train_s", "vram_peak_mb")}
    summary["layers"] = json.load(open(root / "train" / "scores.json"))
    json.dump(summary, open(dest, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
