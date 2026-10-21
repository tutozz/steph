"""r3t5_verify_tok.py <port_trim> <control.jsonl> <tok_orig.json> <map.json> <out.json>

Tokenization check of a trimmed GGUF (R3-T5) against the original, both through llama.cpp.
tok_orig.json: ids of the original model on the same rows (r3t5_tokenize.py).
Per row: `identical` when the trimmed ids, mapped back to original ids, equal the original ids;
`coverable` when every original id is kept, the only rows that can be identical;
`roundtrip` when /detokenize of the trimmed ids gives the text back.

SPDX-License-Identifier: MIT
"""
import json
import sys
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

port, src, orig_path, map_path, dst = sys.argv[1:6]
URL = f"http://127.0.0.1:{port}"


def post(path, body):
    req = urllib.request.Request(URL + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def one(text):
    ids = post("/tokenize", {"content": text, "add_special": False, "parse_special": True})["tokens"]
    back = post("/detokenize", {"tokens": ids})["content"]
    return ids, back


rows = [json.loads(line) for line in open(src, encoding="utf-8")]
orig = json.load(open(orig_path))
old_ids = json.load(open(map_path))["old_ids"]
kept = set(old_ids)
with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(one, [r["text"] for r in rows]))

stats = {}
for row, o, (ids, back) in zip(rows, orig, res):
    s = stats.setdefault(row["src"], Counter())
    cover = all(t in kept for t in o)
    same = [old_ids[t] for t in ids] == o
    s["rows"] += 1
    s["coverable"] += cover
    s["identical"] += same
    s["identical_when_coverable"] += cover and same
    s["different_when_coverable"] += cover and not same
    s["roundtrip"] += back == row["text"]
total = sum(stats.values(), Counter())
out = {"total": dict(total), "by_source": {k: dict(v) for k, v in stats.items()}}
json.dump(out, open(dst, "w"), indent=1)
print(json.dumps(out["total"]))
