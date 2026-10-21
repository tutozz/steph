"""granite_prune_tokenizer.py <tokenizer.json> <map.json> <sortie.json> : tokenizer.json remappé sur le vocabulaire gardé.

SPDX-License-Identifier: MIT
"""
import json
import sys

tj = json.load(open(sys.argv[1]))
old_ids = json.load(open(sys.argv[2]))["old_ids"]
remap = {o: i for i, o in enumerate(old_ids)}
vocab = tj["model"]["vocab"]
tj["model"]["vocab"] = {t: remap[i] for t, i in vocab.items() if i in remap}
kept = set(tj["model"]["vocab"])
pair = lambda m: m.split(" ", 1) if isinstance(m, str) else m
tj["model"]["merges"] = [m for m in tj["model"]["merges"] if (lambda a, b: a in kept and b in kept and a + b in kept)(*pair(m))]
for a in tj["added_tokens"]:
    a["id"] = remap[a["id"]]


def fix(o):
    if isinstance(o, dict):
        if "ids" in o and isinstance(o["ids"], list) and all(isinstance(x, int) for x in o["ids"]):
            o["ids"] = [remap[x] for x in o["ids"]]
        for v in o.values():
            fix(v)
    elif isinstance(o, list):
        for v in o:
            fix(v)


fix(tj.get("post_processor"))
json.dump(tj, open(sys.argv[3], "w"), ensure_ascii=False)
print(len(tj["model"]["vocab"]), len(tj["model"]["merges"]), len(tj["added_tokens"]))
