#!/usr/bin/env python3
"""R2-B1 : synthèse du balayage -ub (médiane des passes, prédiction i5 par ancrage).

Prédiction i5 de chaque -ub : point i5 mesuré de R1 à -ub 64 (Q3 : médiane 0,55 s, p90 2,33 s,
même harnais, mêmes 36 cas) multiplié par le rapport proxy(-ub) / proxy(-ub 64), et
facteur global T4 (2,51) en second avis. IC 95 % du rapport de p90 par bootstrap des cas.
"""

import argparse
import json
import random
import statistics
from pathlib import Path

I5_R1_UB64 = {"p50": 0.55, "p90": 2.33}
T4_FACTOR = 2.51


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def load(res: Path) -> dict:
    runs = {}
    for f in sorted(res.glob("pass*/*.json")):
        d = json.load(open(f))
        if "rows" in d:
            runs.setdefault(d["label"], []).append(d)
    return runs


def per_case(runs: list) -> dict:
    out = {}
    for r in runs:
        for row in r["rows"]:
            if "ttft" in row:
                out.setdefault(row["id"], []).append(row["ttft"])
    return {k: statistics.median(v) for k, v in out.items()}


def boot_ratio(a: dict, b: dict, q: float, n: int = 10000, seed: int = 7):
    ids = sorted(set(a) & set(b))
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        s = [rng.choice(ids) for _ in ids]
        vals.append(pct([a[i] for i in s], q) / pct([b[i] for i in s], q))
    vals.sort()
    return round(vals[int(0.025 * n)], 3), round(vals[int(0.975 * n)], 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("res")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    runs = load(Path(a.res))
    table = []
    for label, rs in sorted(runs.items()):
        cases = per_case(rs)
        row = {
            "label": label, "passes": len(rs),
            "p50": round(statistics.median(cases.values()), 3), "p90": round(pct(cases.values(), 0.9), 3),
            "p50_passes": [r.get("ttft_median") for r in rs], "p90_passes": [r.get("ttft_p90") for r in rs],
            "ram_peak_mb": max(r["ram_peak_mb"] for r in rs),
            "ram_idle_before_mb": max(r["ram_repos_avant_mb"] for r in rs),
            "load_s": statistics.median(r["load_s"] for r in rs),
            "prompt_n": sum(x.get("prompt_n") or 0 for x in rs[0]["rows"]),
            "loadavg_max": max(max(r.get("loadavg_before", 0), r.get("loadavg_after", 0)) for r in rs),
        }
        ref_label = label.replace(f"-ub{label.split('-ub')[1].split('-')[0]}-", "-ub64-", 1)
        ref_label = ref_label.replace("-b192-", "-b512-").replace("-b64-", "-b512-")
        if ref_label in runs and ref_label != label:
            ref = per_case(runs[ref_label])
            row["ratio_p90_vs_ub64"] = round(row["p90"] / pct(ref.values(), 0.9), 3)
            row["ratio_p50_vs_ub64"] = round(row["p50"] / statistics.median(ref.values()), 3)
            row["ci95_p90_ratio"] = boot_ratio(cases, ref, 0.9)
        if label.startswith("r1-") and "r1-ub64-b512-c36" in runs:
            anchor = per_case(runs["r1-ub64-b512-c36"])
            f50 = I5_R1_UB64["p50"] / statistics.median(anchor.values())
            f90 = I5_R1_UB64["p90"] / pct(anchor.values(), 0.9)
            row["factor_i5_p50"], row["factor_i5_p90"] = round(f50, 2), round(f90, 2)
            row["i5_pred_anchor_p50"] = round(row["p50"] * f50, 2)
            row["i5_pred_anchor_p90"] = round(row["p90"] * f90, 2)
            kinds = {x["id"]: x["kind"] for x in rs[0]["rows"]}
            for k in ("summary", "qa"):
                sub = [v for i, v in cases.items() if kinds.get(i) == k]
                if sub:
                    row[f"p90_{k}"] = round(pct(sub, 0.9), 3)
                    row[f"i5_pred_anchor_p90_{k}"] = round(pct(sub, 0.9) * f90, 2)
        row["i5_pred_t4_p50"] = round(row["p50"] * T4_FACTOR, 2)
        row["i5_pred_t4_p90"] = round(row["p90"] * T4_FACTOR, 2)
        table.append(row)
        print(json.dumps(row, ensure_ascii=False))
    json.dump({"anchor_i5_r1_ub64": I5_R1_UB64, "t4_factor": T4_FACTOR, "table": table},
              open(a.out, "w"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
