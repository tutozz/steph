"""r3t5_tokenize.py <port> <in.jsonl> <out.json> [--counts]

Tokenizes each {"text"} row with a running llama-server (/tokenize, specials parsed as in
chat prompts). --counts writes {id: count}; otherwise writes the id list of every row.
Rows may carry "messages" instead of "text": the prompt is then rendered by /apply-template,
exactly as /v1/chat/completions renders it.

SPDX-License-Identifier: MIT
"""
import json
import sys
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

port, src, dst = sys.argv[1:4]
counts_only = "--counts" in sys.argv
URL = f"http://127.0.0.1:{port}"


def post(path, body):
    req = urllib.request.Request(URL + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def one(row):
    text = row.get("text")
    if text is None:
        text = post("/apply-template", {"messages": row["messages"], "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
    return post("/tokenize", {"content": text, "add_special": False, "parse_special": True})["tokens"]


rows = [json.loads(line) for line in open(src, encoding="utf-8")]
with ThreadPoolExecutor(8) as ex:
    ids = list(ex.map(one, rows))
if counts_only:
    c = Counter(t for seq in ids for t in seq)
    json.dump({"rows": len(rows), "tokens": sum(c.values()), "counts": {str(k): v for k, v in c.items()}}, open(dst, "w"))
    print(f"{len(rows)} rows, {sum(c.values())} tokens, {len(c)} distinct ids")
else:
    json.dump(ids, open(dst, "w"))
    print(f"{len(rows)} rows, {sum(map(len, ids))} tokens")
