"""Judge the resolve() sentences with the A7 judge (2 passes), raw output as context.

SPDX-License-Identifier: MIT
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/root/stephbench-matrix/judge")
from run_fixed import process_one

rows = json.load(open(sys.argv[1]))
with ThreadPoolExecutor(max_workers=4) as ex:
    results = list(ex.map(
        lambda r: process_one("resolve", {"id": r["id"], "kind": "summary", "out": r["resolved"]}, r["context"]),
        rows))
json.dump(results, open(sys.argv[2], "w"), ensure_ascii=False, indent=2)
print(len(results), {v: sum(r["final"] == v for r in results) for v in {r["final"] for r in results}})
