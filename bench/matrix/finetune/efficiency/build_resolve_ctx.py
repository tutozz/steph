"""Rebuild resolve() sentences with their full raw output as judge context.

SPDX-License-Identifier: MIT
"""
import json
from pathlib import Path

import steph.digest as dg
from steph.prompts import summary_messages

ROOT = Path(__file__).resolve().parents[4]
fx = json.load(open(ROOT / "bench/fixtures.json")) + json.load(open(ROOT / "bench/extra_fixtures.json"))
for extra, cmd in (("df_proxmox.txt", "df -h"), ("ip_a_proxmox.txt", "ip a")):
    fx.append({"cmd": cmd, "exit": 0, "duration": 0.1, "output": (ROOT / "tests/data" / extra).read_text(),
               "id": extra[:-4]})
rows = []
for i, f in enumerate(fx):
    cid = f.get("id") or f"fx{i:02d}"
    said = dg.resolve(f["cmd"], f["exit"], f["output"])
    if not said:
        continue
    ctx = summary_messages(f["cmd"], f["exit"], f["duration"], f["output"], len(f["output"].splitlines()))[1]["content"]
    rows.append({"id": cid, "resolved": said, "context": ctx})
json.dump(rows, open(__import__("sys").argv[1], "w"), ensure_ascii=False, indent=2)
print(len(rows), max(len(r["context"]) for r in rows))
