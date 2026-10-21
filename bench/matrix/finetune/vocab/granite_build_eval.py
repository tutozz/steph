"""Rassemble les entrées du banc steph et de TermSpeak (FR et EN) en messages de chat.

SPDX-License-Identifier: MIT
"""
import json, sys
from pathlib import Path
sys.path.insert(0, "benchmark")
import run

def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values(): yield from strings(v)
    elif isinstance(o, list):
        for v in o: yield from strings(v)

out = open(sys.argv[1], "w", encoding="utf-8")
cfg = run.load_config(Path("benchmark/data/v1"))
n = 0
for lang in ("fr", "en"):
    for c in run.load_cases(Path("benchmark/data/v1"), lang):
        out.write(json.dumps({"src": f"termspeak-{lang}", "messages": run.build_messages(c, cfg["prompts"]),
                              "texts": list(strings(c))}, ensure_ascii=False) + "\n"); n += 1
for c in json.load(open("bench/matrix/cases.json")):
    out.write(json.dumps({"src": "steph-cases", "messages": c["messages"], "texts": list(strings(c))}, ensure_ascii=False) + "\n"); n += 1
out.write(json.dumps({"src": "steph-facts", "messages": [], "texts": list(strings(json.load(open("bench/matrix/facts.json"))))}, ensure_ascii=False) + "\n")
out.write(json.dumps({"src": "termspeak-prompts", "messages": [], "texts": list(strings(cfg))}, ensure_ascii=False) + "\n")
print(n)
