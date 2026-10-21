"""granite_verify.py <dossier_tokenizer> <tokenizer-réduit.json> <map.json> <f1.jsonl> [...]

Compare, texte par texte, la tokenisation complète remappée à la tokenisation réduite.
Sort des comptes par source : textes, jetons (complet et réduit), jetons hors vocabulaire gardé, textes différents.

SPDX-License-Identifier: MIT
"""
import json
import sys

from tokenizers import Tokenizer
from transformers import AutoTokenizer

hf = AutoTokenizer.from_pretrained(sys.argv[1])
full = Tokenizer.from_file(sys.argv[1] + "/tokenizer.json")
small = Tokenizer.from_file(sys.argv[2])
remap = {o: i for i, o in enumerate(json.load(open(sys.argv[3]))["old_ids"])}
import collections
st = collections.defaultdict(lambda: {"texts": 0, "tokens": 0, "tokens_reduced": 0, "unknown": 0, "different": 0})
for path in sys.argv[4:]:
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        s = st[d.get("src", path.rsplit("/", 1)[-1])]
        m = d.get("messages") or []
        texts = list(d.get("texts") or []) + [x["content"] for x in m]
        if m:
            texts.append(hf.apply_chat_template(m, tokenize=False))
            texts.append(hf.apply_chat_template(m[:-1] if m[-1]["role"] == "assistant" else m, tokenize=False, add_generation_prompt=True))
        for t in texts:
            a = full.encode(t, add_special_tokens=False).ids
            b = small.encode(t, add_special_tokens=False).ids
            s["texts"] += 1; s["tokens"] += len(a); s["tokens_reduced"] += len(b)
            s["unknown"] += sum(1 for x in a if x not in remap)
            s["different"] += [remap.get(x, -1) for x in a] != b
tot = {k: sum(v[k] for v in st.values()) for k in ("texts", "tokens", "tokens_reduced", "unknown", "different")}
print(json.dumps({"by_source": st, "total": tot}))
