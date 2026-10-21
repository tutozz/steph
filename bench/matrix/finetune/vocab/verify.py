"""verify.py <tok_full.json> <tok_reduced.json> <reduced.gguf.map.json> : token-by-token comparison
per source, after mapping reduced ids back to the full vocabulary.

SPDX-License-Identifier: MIT
"""
import collections, json, sys

full = json.load(open(sys.argv[1]))["texts"]
red = json.load(open(sys.argv[2]))["texts"]
old = json.load(open(sys.argv[3]))
stats = collections.defaultdict(lambda: {"texts": 0, "tokens": 0, "texts_diff": 0, "unk": 0})
for a, b in zip(full, red, strict=True):
    s = stats[a["src"]]
    s["texts"] += 1
    s["tokens"] += len(a["ids"])
    mapped = [old[i] for i in b["ids"]]
    s["unk"] += sum(1 for i in mapped if i == 3)
    if mapped != a["ids"]:
        s["texts_diff"] += 1
print(json.dumps(stats, indent=1))
print("TOTAL_DIFF", sum(s["texts_diff"] for s in stats.values()), "TOTAL_UNK", sum(s["unk"] for s in stats.values()))
