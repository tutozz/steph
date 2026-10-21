"""ood.py <ood.json> <port_full> <port_reduced> <reduced.map.json> : token inflation and byte fallbacks on texts outside the vocabulary selection.

SPDX-License-Identifier: MIT
"""
import json, sys, urllib.request


def tok(port, text):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/tokenize", json.dumps(
        {"content": text, "add_special": False, "parse_special": False, "with_pieces": True}).encode(),
        {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))["tokens"]


OLD = json.load(open(sys.argv[4]))


def is_byte(old_id):
    return 238 <= old_id <= 493


for name, texts in json.load(open(sys.argv[1])).items():
    nf = nr = bf = br = same = 0
    for t in texts:
        a, b = tok(sys.argv[2], t), tok(sys.argv[3], t)
        nf += len(a); nr += len(b)
        same += [p["id"] for p in a] == [OLD[p["id"]] for p in b]
        bf += sum(is_byte(p["id"]) for p in a); br += sum(is_byte(OLD[p["id"]]) for p in b)
    print(json.dumps({"set": name, "texts": len(texts), "identical": same, "tokens_full": nf, "tokens_reduced": nr,
                      "inflation_pct": round(100 * (nr - nf) / max(nf, 1), 2), "byte_tokens_full": bf, "byte_tokens_reduced": br}))
