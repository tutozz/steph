#!/usr/bin/env python3
"""G4 : résumé des mesures i5 (bench_run.py, production generic, 51 résumés dev v3 reaches_model).

    python3 g4_i5.py <res/> <out.json>

SPDX-License-Identifier: MIT
"""

import json
import statistics
import sys
from pathlib import Path


def main():
    out = {}
    for p in sorted(Path(sys.argv[1]).glob("*.json")):
        if p.name.endswith(".progress.json"):
            continue
        r = json.load(open(p))
        rows = [x for x in r["rows"] if "ttft" in x]
        tt = sorted(x["ttft"] for x in rows)
        out[p.stem] = {"n": len(rows), "load_s": r["load_s"], "ttft_median": r["ttft_median"], "ttft_p90": r["ttft_p90"],
                       "ttft_max": tt[-1], "ttft_mean": round(statistics.mean(tt), 2), "total_median": r["total_median"],
                       "gen_tok_s_median": r["gen_tok_s_median"], "ram_peak_mb": r["ram_peak_mb"]}
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
    for k, v in out.items():
        print(f"{k:12s} {v}")


if __name__ == "__main__":
    main()
