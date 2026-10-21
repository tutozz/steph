#!/usr/bin/env python3
"""Leaderboard table from benchmark/results/*.json.

    python3 benchmark/tools/leaderboard.py                 # print markdown
    python3 benchmark/tools/leaderboard.py --update-readme # rewrite the table in both READMEs

--dir and --marker target a different results directory and README section, e.g. a
non-standard protocol that must stay out of the main table:

    python3 benchmark/tools/leaderboard.py --dir results/steph-protocol \\
        --marker steph-protocol --update-readme

Only measured values are shown; a missing measure stays empty.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]


def cell(value, fmt="{}") -> str:
    return "" if value is None else fmt.format(value)


def rows(split: str, directory: Path | None = None) -> list:
    """Rows from directory's *.json (default results/: the main leaderboard). A directory
    outside results/ (e.g. results/steph-protocol/) never feeds the main table: only an
    explicit --dir reads it."""
    directory = directory or (BENCH / "results")
    link_dir = os.path.relpath(directory, BENCH)
    out = []
    for path in sorted(directory.glob("*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        if r.get("split") != split:
            continue
        s, hw = r["summary"], r.get("hardware") or {}
        gpu = hw.get("gpu") or []
        gpu_name = gpu[0] if gpu and not gpu[0].startswith(str(hw.get("cpu"))) else None
        ram = f"{hw['ram_gb']:g} GB" if hw.get("ram_gb") else None
        hardware = r.get("hardware_note") or ", ".join(x for x in [hw.get("cpu"), gpu_name, ram] if x)
        backend = r.get("backend") or {}
        judge = (r.get("judge") or {}).get("summary") or {}
        out.append({
            "model": r["model"]["label"], "lang": r["lang"], "score": s["score"],
            "recall": s["fact_recall"], "forbidden": s["forbidden_rate"],
            "judge": judge.get("hallucination_rate"),
            "ttft": s.get("ttft_median_s"), "p90": s.get("ttft_p90_s"), "tok": s.get("tok_s_median"),
            "backend": " ".join(str(x) for x in [backend.get("name"), backend.get("version")] if x),
            "hardware": hardware, "file": path.name, "link": f"{link_dir}/{path.name}",
        })
    return sorted(out, key=lambda x: (x["lang"], -(x["score"] or 0)))


def table(split: str, directory: Path | None = None) -> str:
    lines = ["| Model | Lang | Score | Fact recall | Forbidden hit | Judge: hallucinated | TTFT median (s) "
             "| TTFT p90 (s) | tok/s | Backend | Hardware | Result file |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|"]
    for x in rows(split, directory):
        lines.append(f"| {x['model']} | {x['lang']} | {cell(x['score'], '{:.1f}')} | {cell(x['recall'], '{:.1f}')} "
                     f"| {cell(x['forbidden'], '{:.1f} %')} | {cell(x['judge'], '{:.1f} %')} | {cell(x['ttft'])} "
                     f"| {cell(x['p90'])} | {cell(x['tok'])} | {x['backend']} | {x['hardware']} "
                     f"| [{x['file']}]({x['link']}) |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["dev", "test"])
    ap.add_argument("--dir", default="results",
                     help="results directory, relative to benchmark/ (default: results, the main table)")
    ap.add_argument("--marker", default="leaderboard",
                     help="README comment marker to replace, <!-- NAME:start/end --> (default: leaderboard)")
    ap.add_argument("--update-readme", action="store_true")
    a = ap.parse_args()
    md = table(a.split, BENCH / a.dir)
    if not a.update_readme:
        print(md)
        return 0
    start, end = f"<!-- {a.marker}:start -->", f"<!-- {a.marker}:end -->"
    for name in ("README.md", "README.fr.md"):
        path = BENCH / name
        text = path.read_text(encoding="utf-8")
        new = re.sub(re.escape(start) + r".*?" + re.escape(end), f"{start}\n{md}\n{end}", text, flags=re.S)
        path.write_text(new, encoding="utf-8")
        print(f"updated {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
