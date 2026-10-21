#!/usr/bin/env python3
"""G6 : tableau de vitesse i5 des MoE bruts (36 cas, résumés dev v3 generic, questions P20), à partir de
i5/res/. Retire d'abord les sorties du modèle des JSON (--strip), comme en G2.

    python3 i5_summary.py <i5/res> [--strip]

SPDX-License-Identifier: MIT
"""

import json
import statistics as st
import sys
from pathlib import Path


def p90(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(0.9 * len(xs)))] if xs else None


def pp_rate(rows):
    r = [x["prompt_n"] / x["prompt_ms"] * 1000 for x in rows if x.get("prompt_ms") and (x.get("prompt_n") or 0) > 50]
    return round(st.median(r), 1) if r else None


def fmt(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}".replace(".", ",")


def main():
    res = Path(sys.argv[1])
    if "--strip" in sys.argv:
        for p in res.glob("*.json"):
            d = json.load(open(p))
            rows = d.get("rows") if isinstance(d, dict) else None
            if rows and any("out" in r for r in rows):
                for r in rows:
                    r.pop("out", None)
                json.dump(d, open(p, "w"), ensure_ascii=False, indent=1)
    labels = sorted({p.name[: -len("-36.json")] for p in res.glob("*-36.json")})
    print("| Modèle | Chargement | RAM pic 36 cas / résumés | Lecture prompt (j/s) | Génération (j/s) "
          "| 36 cas méd. / p90 | Résumés dev méd. / p90 | Questions froid p90 | Préchauffé p90 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for lab in labels:
        a = json.load(open(res / f"{lab}-36.json"))
        s = json.load(open(res / f"{lab}-sum-dev.json")) if (res / f"{lab}-sum-dev.json").exists() else {}
        qa = {}
        for reg in ("cold", "warm"):
            q = res / f"{lab}-qa-{reg}.json"
            if q.exists():
                d = json.load(open(q))
                rows = d["rows"] if isinstance(d, dict) else d
                qa[reg] = p90([r["ttft"] for r in rows if r.get("ttft") is not None])
        err = a.get("error") or s.get("error")
        print(f"| {lab} | {fmt(a.get('load_s'))} s | {a.get('ram_peak_mb', '-')} / {s.get('ram_peak_mb', '-')} Mo "
              f"| {fmt(pp_rate(s.get('rows', [])), 1)} | {fmt(s.get('gen_tok_s_median'), 1)} "
              f"| {fmt(a.get('ttft_median'))} / {fmt(a.get('ttft_p90'))} s "
              f"| {fmt(s.get('ttft_median'))} / {fmt(s.get('ttft_p90'))} s | {fmt(qa.get('cold'))} | {fmt(qa.get('warm'))} |"
              + (f" erreur : {err[:60]}" if err else ""))


if __name__ == "__main__":
    main()
