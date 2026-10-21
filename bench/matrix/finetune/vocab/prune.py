"""prune.py <src.gguf> <tok_full.json> <target> <dst.gguf> : keeps the tokens used by the texts,
every SPM merge intermediate needed to rebuild them, specials, byte fallbacks and user-defined
tokens, then fills up to <target> with the highest-score tokens. Writes a GGUF with the
token_embd rows and tokenizer arrays reduced accordingly, and <dst>.map.json (new -> old id).

SPDX-License-Identifier: MIT
"""
import heapq, json, sys
import numpy as np
import gguf

NORMAL, UNKNOWN, CONTROL, USER_DEFINED, UNUSED, BYTE = 1, 2, 3, 4, 5, 6
src, tokfile, target, dst = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]

r = gguf.GGUFReader(src)
toks = r.fields["tokenizer.ggml.tokens"].contents()
scores = r.fields["tokenizer.ggml.scores"].contents()
types = r.fields["tokenizer.ggml.token_type"].contents()
tok2id = {t: i for i, t in enumerate(toks)}


def spm(text):
    """llama.cpp llm_tokenizer_spm on one fragment: returns (final ids, merge-created ids)."""
    sym = list(text)
    n = len(sym)
    nb = [len(s.encode()) for s in sym]
    prev = list(range(-1, n - 1))
    nxt = list(range(1, n + 1))
    nxt[-1] = -1
    heap, created = [], set()

    def add(left, right):
        if left < 0 or right < 0:
            return
        t = sym[left] + sym[right]
        i = tok2id.get(t)
        if i is None:
            return
        heapq.heappush(heap, (-scores[i], left, right, len(t.encode()), i))

    for k in range(1, n):
        add(k - 1, k)
    while heap:
        _, left, right, size, i = heapq.heappop(heap)
        if nb[left] == 0 or nb[right] == 0 or nb[left] + nb[right] != size:
            continue
        sym[left] += sym[right]
        nb[left] += nb[right]
        nb[right] = 0
        nxt[left] = nxt[right]
        if nxt[right] >= 0:
            prev[nxt[right]] = left
        created.add(i)
        add(prev[left], left)
        add(left, nxt[left])
    final, k = [], 0
    while k != -1 and n:
        i = tok2id.get(sym[k])
        final += [i] if i is not None else [tok2id["<0x%02X>" % b] for b in sym[k].encode()]
        k = nxt[k]
    return final, created


texts = json.load(open(tokfile))["texts"]
used = set()
for t in texts:
    used.update(t["ids"])

keep = set(i for i in range(len(toks)) if types[i] in (BYTE, USER_DEFINED))
keep |= set(i for i in range(len(toks)) if types[i] == CONTROL and not toks[i].startswith("<unused")
            and "image" not in toks[i] and "audio" not in toks[i])
for key in ("bos", "eos", "unknown", "padding"):
    keep.add(int(r.fields[f"tokenizer.ggml.{key}_token_id"].contents()))
keep |= used

not_self = 0
for i in sorted(used):
    if types[i] != NORMAL:
        continue
    final, created = spm(toks[i])
    if final != [i]:
        not_self += 1
    keep |= created

n_used, n_closed = len(used), len(keep)
for i in sorted((i for i in range(len(toks)) if types[i] == NORMAL), key=lambda i: -scores[i]):
    if len(keep) >= target:
        break
    if i in keep:
        continue
    final, created = spm(toks[i])
    if final == [i]:
        keep.add(i)
        keep |= created

old = sorted(keep)
new_of = {o: k for k, o in enumerate(old)}
print(json.dumps({"vocab_full": len(toks), "used": n_used, "used_plus_closure_specials": n_closed,
                  "used_not_self_tokenizing": not_self, "kept": len(old)}))

w = gguf.GGUFWriter(dst, "gemma3")
for f in r.fields.values():
    if f.name == gguf.Keys.General.ARCHITECTURE or f.name.startswith("GGUF."):
        continue
    vt = f.types[0]
    sub = f.types[-1] if vt == gguf.GGUFValueType.ARRAY else None
    val = f.contents()
    if f.name == "tokenizer.ggml.tokens":
        val = [toks[o] for o in old]
    elif f.name == "tokenizer.ggml.scores":
        val = [scores[o] for o in old]
    elif f.name == "tokenizer.ggml.token_type":
        val = [types[o] for o in old]
    elif f.name.startswith("tokenizer.ggml.") and f.name.endswith("_token_id"):
        val = new_of[int(val)]
    w.add_key_value(f.name, val, vt, sub_type=sub)
for t in r.tensors:
    data = np.asarray(t.data)
    if t.name == "token_embd.weight":
        data = np.ascontiguousarray(data[old])
    w.add_tensor(t.name, data)
w.write_header_to_file()
w.write_kv_data_to_file()
w.write_tensors_to_file()
w.close()
json.dump(old, open(dst + ".map.json", "w"))
