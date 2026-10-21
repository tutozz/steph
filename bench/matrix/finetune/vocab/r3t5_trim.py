"""r3t5_trim.py <in.gguf> <out.gguf> <target> --must <counts.json> [...] --rank <counts.json> [...]

Trims the vocabulary of a byte-level BPE GGUF straight from its quantized tensors (R3-T5).
Kept: special and single-character tokens, every id of the --must files (production format),
then ids of the --rank files by decreasing count until <target>, each with its merge closure
(both parents of any merge producing a kept token are kept). A string whose original
tokenization uses kept ids only tokenizes identically after trimming.
token_embd rows are sliced as raw quantized bytes: kept rows are bit-identical to the source.

SPDX-License-Identifier: MIT
"""
import argparse
import json

import numpy as np
import gguf

def load_counts(paths):
    c = {}
    for p in paths:
        for k, v in json.load(open(p))["counts"].items():
            c[int(k)] = c.get(int(k), 0) + v
    return c


def select(tokens, ttypes, merges, must, ranked, target):
    """Kept ids: specials, single characters, must ids, then ranked ids until target, all merge-closed."""
    index = {t: i for i, t in enumerate(tokens)}
    producers = {}
    for m in merges:
        x, y = m.split(" ", 1)
        producers.setdefault(x + y, []).append((x, y))
    keep = {i for i, t in enumerate(ttypes) if t != gguf.TokenType.NORMAL}
    keep |= {i for i, t in enumerate(tokens) if len(t) == 1}

    def close(start):
        stack = list(start)
        while stack:
            for x, y in producers.get(tokens[stack.pop()], []):
                for part in (x, y):
                    j = index.get(part)
                    if j is not None and j not in keep:
                        keep.add(j)
                        stack.append(j)

    keep |= set(must)
    close(set(keep))
    n_must = len(keep)
    for i in sorted(ranked, key=lambda k: (-ranked[k], k)):
        if len(keep) >= target:
            break
        if i not in keep:
            keep.add(i)
            close([i])
    return keep, n_must


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("target", type=int)
    ap.add_argument("--must", nargs="*", default=[])
    ap.add_argument("--rank", nargs="*", default=[])
    a = ap.parse_args()

    reader = gguf.GGUFReader(a.src, "r")
    F = reader.fields
    tokens = F["tokenizer.ggml.tokens"].contents()
    ttypes = F["tokenizer.ggml.token_type"].contents()
    merges = F["tokenizer.ggml.merges"].contents()
    n = len(tokens)
    keep, n_must = select(tokens, ttypes, merges, load_counts(a.must), load_counts(a.rank), a.target)

    old_ids = sorted(keep)
    remap = {o: i for i, o in enumerate(old_ids)}
    kept = {tokens[o] for o in old_ids}
    new_merges = [m for m in merges if (lambda x, y: x in kept and y in kept and x + y in kept)(*m.split(" ", 1))]

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
            rewritten[name] = remap[f.contents()]
    arch = F["general.architecture"].contents()
    if f"{arch}.vocab_size" in F:
        rewritten[f"{arch}.vocab_size"] = len(old_ids)

    writer = gguf.GGUFWriter(a.dst, arch=arch, endianess=reader.endianess)
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
            assert d.shape[0] == n, (t.name, d.shape)
            d = np.ascontiguousarray(d[idx])
        datas.append(d)
        writer.add_tensor_info(t.name, d.shape, d.dtype, d.nbytes, t.tensor_type)
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_ti_data_to_file()
    for d in datas:
        writer.write_tensor_data(d, tensor_endianess=reader.endianess)
    writer.close()

    json.dump({"vocab_before": n, "vocab_after": len(old_ids), "must_with_closure": n_must, "target": a.target,
               "merges_before": len(merges), "merges_after": len(new_merges), "old_ids": old_ids}, open(a.dst + ".map.json", "w"))
    print(f"vocab {n} -> {len(old_ids)} (must+closure {n_must}), merges {len(merges)} -> {len(new_merges)}")


if __name__ == "__main__":
    main()
