"""granite_token_ids.py <dossier_tokenizer> <sortie.json> <f1.jsonl> [...] : identifiants de jetons utilisés.

Chaque ligne porte "messages" (rendus par le gabarit de chat, conversation complète et invite seule)
et éventuellement "texts" (encodés seuls). Seule la liste d'identifiants et leurs comptes sortent.

SPDX-License-Identifier: MIT
"""
import json, sys, collections
from transformers import AutoTokenizer

tok = AutoTokenizer.from_pretrained(sys.argv[1])
cnt = collections.Counter()
lines = 0
for path in sys.argv[3:]:
    for line in open(path, encoding="utf-8"):
        d = json.loads(line); lines += 1
        m = d.get("messages") or []
        if m:
            cnt.update(tok.apply_chat_template(m, tokenize=True, return_dict=False))
            if m[-1]["role"] == "assistant":
                cnt.update(tok.apply_chat_template(m[:-1], tokenize=True, add_generation_prompt=True, return_dict=False))
            else:
                cnt.update(tok.apply_chat_template(m, tokenize=True, add_generation_prompt=True, return_dict=False))
            for x in m:
                cnt.update(tok.encode(x["content"], add_special_tokens=False))
        for t in d.get("texts") or []:
            cnt.update(tok.encode(t, add_special_tokens=False))
            cnt.update(tok.encode(" " + t, add_special_tokens=False))
json.dump({"lines": lines, "vocab_size": len(tok), "ids": sorted(cnt), "counts": {str(k): v for k, v in sorted(cnt.items())}}, open(sys.argv[2], "w"))
print(f"{lines} lignes, {len(cnt)} jetons distincts sur {len(tok)}")
