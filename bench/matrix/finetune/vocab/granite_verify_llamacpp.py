"""granite_verify_llamacpp.py <port_complet> <port_réduit> <réduit.map.json> <dossier_tokenizer_hf> <f1.jsonl> [...]

Tokenisation llama.cpp (/apply-template puis /tokenize) du modèle complet et du modèle réduit,
comparée jeton par jeton après remappage, et accord llama.cpp complet contre Hugging Face.

SPDX-License-Identifier: MIT
"""
import collections
import json
import sys
import urllib.request

from tokenizers import Tokenizer


def post(port, path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


pf, pr = sys.argv[1], sys.argv[2]
old_ids = json.load(open(sys.argv[3]))["old_ids"]
hf = Tokenizer.from_file(sys.argv[4] + "/tokenizer.json")
st = collections.defaultdict(lambda: {"texts": 0, "tokens": 0, "tokens_reduced": 0, "different": 0, "hf_mismatch": 0})
for path in sys.argv[5:]:
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        s = st[d.get("src", path.rsplit("/", 1)[-1])]
        m = d.get("messages") or []
        items = [(t, False) for t in d.get("texts") or []] + [(x["content"], False) for x in m]
        if m:
            p = m[:-1] if m[-1]["role"] == "assistant" else m
            items.append((post(pf, "/apply-template", {"messages": p})["prompt"], True))
        for text, special in items:
            a = post(pf, "/tokenize", {"content": text, "add_special": False, "parse_special": special})["tokens"]
            b = post(pr, "/tokenize", {"content": text, "add_special": False, "parse_special": special})["tokens"]
            s["texts"] += 1; s["tokens"] += len(a); s["tokens_reduced"] += len(b)
            s["different"] += [old_ids[i] for i in b] != a
            if not special:
                s["hf_mismatch"] += hf.encode(text, add_special_tokens=False).ids != a
tot = {k: sum(v[k] for v in st.values()) for k in ("texts", "tokens", "tokens_reduced", "different", "hf_mismatch")}
print(json.dumps({"by_source": st, "total": tot}))
