#!/usr/bin/env python3
"""R2-B1 : balayage -ub de llama-server, réglages de production sinon.

Chaque configuration passe par bench/perf/granite_ram.py (même harnais que la mesure i5 de
référence Q3) ; ordre des configurations tiré au hasard à chaque passe. Le processus doit
être épinglé par l'appelant (taskset ou systemd-run) : llama-server hérite de l'affinité.
"""

import argparse
import json
import random
import subprocess
import time
from pathlib import Path

UBATCHES = (64, 96, 128, 192, 256, 512)
PROD = {"ctx": 8192, "parallel": 2, "extra": "--cache-ram 0"}
# P14 shape of the i5 anchor 1.299 s (P17, -ub 512) and of Q2c (P15, -ub 64)
P14 = {"ctx": 4096, "parallel": 1, "extra": ""}


def configs(r1: str, p17: str) -> list[dict]:
    out = []
    for ub in UBATCHES:
        for cs in ("c36", "dev60"):
            out.append({"label": f"r1-ub{ub}-b512-{cs}", "model": r1, "cases": cs, "ub": ub, "b": 512, **PROD})
    for ub in (64, 192):
        out.append({"label": f"r1-ub{ub}-b{ub}-c36", "model": r1, "cases": "c36", "ub": ub, "b": ub, **PROD})
    for ub in (64, 512):
        out.append({"label": f"p17-p14shape-ub{ub}-c36", "model": p17, "cases": "c36", "ub": ub, "b": 512, **P14})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--r1", required=True)
    ap.add_argument("--p17", required=True)
    ap.add_argument("--c36", required=True)
    ap.add_argument("--dev60", required=True)
    ap.add_argument("--harness", required=True, help="granite_ram.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()

    rng = random.Random(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = {"c36": (a.c36, 1500), "dev60": (a.dev60, 0)}
    for p in range(1, a.passes + 1):
        todo = configs(a.r1, a.p17)
        rng.shuffle(todo)
        for c in todo:
            path, maxc = cases[c["cases"]]
            dst = out / f"pass{p}" / f"{c['label']}.json"
            if dst.exists():
                continue
            load = open("/proc/loadavg").read().split()[0]
            cmd = ["python3", a.harness, "--server", a.server, "--model", c["model"], "--label", c["label"],
                   "--out", str(dst), "--cases", path, "--maxc", str(maxc), "--threads", "4",
                   "--ctx", str(c["ctx"]), "--batch", str(c["b"]), "--ubatch", str(c["ub"]),
                   "--parallel", str(c["parallel"])]
            if c["extra"]:
                cmd += ["--extra", c["extra"]]
            t0 = time.time()
            subprocess.run(cmd, check=False)
            res = json.load(open(dst)) if dst.exists() else {}
            res.update({"pass": p, "loadavg_before": float(load),
                        "loadavg_after": float(open("/proc/loadavg").read().split()[0]),
                        "wall_s": round(time.time() - t0, 1)})
            json.dump(res, open(dst, "w"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
