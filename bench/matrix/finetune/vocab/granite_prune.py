"""granite_prune.py <entrée.gguf> <sortie.gguf> <cible> <ids1.json> [ids2.json ...]

Réduit le vocabulaire d'un GGUF BPE (octets) aux jetons utilisés, plus jetons spéciaux,
les 256 jetons d'un octet et la fermeture des fusions : tout parent d'une fusion qui produit
un jeton gardé est gardé, ce qui rend la tokenisation identique sur les textes d'origine.
Complète ensuite jusqu'à <cible> jetons dans l'ordre des rangs BPE (identifiant croissant), avec
leur fermeture. Élague token_embd (et output s'il existe), remappe tokens, types, fusions et identifiants spéciaux.

SPDX-License-Identifier: MIT
"""
import json
import sys

import numpy as np
import gguf

src, dst, target, id_files = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4:]
reader = gguf.GGUFReader(src, "r")
F = reader.fields
tokens = F["tokenizer.ggml.tokens"].contents()
ttypes = F["tokenizer.ggml.token_type"].contents()
merges = F["tokenizer.ggml.merges"].contents()
n = len(tokens)
index = {t: i for i, t in enumerate(tokens)}

used = set()
for p in id_files:
    used |= set(json.load(open(p))["ids"])

byte_chars = set()
bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
cs, k = bs[:], 0
for b in range(256):
    if b not in bs:
        bs.append(b); cs.append(256 + k); k += 1
byte_chars = {chr(c) for c in cs}

keep = set(used)
keep |= {i for i, t in enumerate(ttypes) if t != gguf.TokenType.NORMAL}
keep |= {index[c] for c in byte_chars if c in index}
missing_bytes = [c for c in byte_chars if c not in index]

producers = {}
for m in merges:
    a, b = m.split(" ", 1)
    producers.setdefault(a + b, []).append((a, b))



def close(start):
    stack = list(start)
    while stack:
        t = tokens[stack.pop()]
        for a, b in producers.get(t, []):
            for part in (a, b):
                j = index.get(part)
                if j is not None and j not in keep:
                    keep.add(j); stack.append(j)


close(keep)
n_closed = len(keep)
for i in range(n):
    if len(keep) >= target:
        break
    if i not in keep and ttypes[i] == gguf.TokenType.NORMAL:
        keep.add(i); close([i])

old_ids = sorted(keep)
remap = {o: i for i, o in enumerate(old_ids)}
kept_tokens = {tokens[o] for o in old_ids}
new_merges = [m for m in merges if (lambda a, b: a in kept_tokens and b in kept_tokens and a + b in kept_tokens)(*m.split(" ", 1))]

rewritten = {
    "tokenizer.ggml.tokens": [tokens[o] for o in old_ids],
    "tokenizer.ggml.token_type": [int(ttypes[o]) for o in old_ids],
    "tokenizer.ggml.merges": new_merges,
}
if "tokenizer.ggml.scores" in F:
    sc = F["tokenizer.ggml.scores"].contents()
    rewritten["tokenizer.ggml.scores"] = [sc[o] for o in old_ids]
for name, f in F.items():
    if name.startswith("tokenizer.ggml.") and name.endswith("_token_id"):
        old = f.contents()
        if old not in remap:
            sys.exit(f"{name}={old} absent du vocabulaire gardé")
        rewritten[name] = remap[old]
arch = F["general.architecture"].contents()
if f"{arch}.vocab_size" in F:
    rewritten[f"{arch}.vocab_size"] = len(old_ids)

writer = gguf.GGUFWriter(dst, arch=arch, endianess=reader.endianess)
for name, f in F.items():
    if name == "general.architecture" or name.startswith("GGUF."):
        continue
    vtype = f.types[0]
    sub = f.types[-1] if vtype == gguf.GGUFValueType.ARRAY else None
    writer.add_key_value(name, rewritten.get(name, f.contents()), vtype, sub_type=sub)

idx = np.array(old_ids, dtype=np.int64)
datas = []
for t in reader.tensors:
    d = t.data
    if t.name in ("token_embd.weight", "output.weight"):
        if t.tensor_type not in (gguf.GGMLQuantizationType.F16, gguf.GGMLQuantizationType.F32, gguf.GGMLQuantizationType.BF16):
            sys.exit(f"{t.name} en {t.tensor_type.name} : élaguer depuis un GGUF f16/f32")
        if d.shape[0] != n:
            sys.exit(f"{t.name} forme {d.shape}, attendu {n} lignes")
        d = np.ascontiguousarray(d[idx])
    datas.append(d)
    writer.add_tensor_info(t.name, d.shape, d.dtype, d.nbytes, t.tensor_type)
writer.write_header_to_file()
writer.write_kv_data_to_file()
writer.write_ti_data_to_file()
for d in datas:
    writer.write_tensor_data(d, tensor_endianess=reader.endianess)
writer.close()

json.dump({"vocab_before": n, "vocab_after": len(old_ids), "used": len(used), "used_plus_closure": n_closed, "target": target, "merges_before": len(merges),
           "merges_after": len(new_merges), "missing_byte_tokens": len(missing_bytes),
           "tensors_pruned": [t.name for t in reader.tensors if t.name in ("token_embd.weight", "output.weight")],
           "old_ids": old_ids}, open(dst + ".map.json", "w"))
print(f"vocabulaire {n} -> {len(old_ids)} (utilisés {len(used)}, avec fermeture {n_closed}), fusions {len(merges)} -> {len(new_merges)}, "
      f"octets manquants {len(missing_bytes)}, élagués {[t.name for t in reader.tensors if t.name in ('token_embd.weight', 'output.weight')]}")
