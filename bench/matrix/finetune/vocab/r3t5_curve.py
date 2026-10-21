"""r3t5_curve.py <model.gguf> <must.json> <rank.json> <tok.json>[:label] [...] --targets 32768 48000 ...

Share of strings whose original tokenization only uses kept ids, for each vocabulary target of
r3t5_trim.select. Such strings tokenize identically after trimming (merge closure), the others
never do (checked on the public control set), so this is the identity rate without building a GGUF.
Also gives the Q4_K_M size of each target (token_embd rows are sliced, nothing else changes).

SPDX-License-Identifier: MIT
"""
import argparse
import json
import os

import gguf

from r3t5_trim import load_counts, select

ap = argparse.ArgumentParser()
ap.add_argument("model")
ap.add_argument("must")
ap.add_argument("rank")
ap.add_argument("toks", nargs="+")
ap.add_argument("--targets", nargs="+", type=int, required=True)
a = ap.parse_args()

reader = gguf.GGUFReader(a.model, "r")
F = reader.fields
tokens = F["tokenizer.ggml.tokens"].contents()
ttypes = F["tokenizer.ggml.token_type"].contents()
merges = F["tokenizer.ggml.merges"].contents()
emb = next(t for t in reader.tensors if t.name == "token_embd.weight")
row_bytes = emb.n_bytes // len(tokens)
size = os.path.getsize(a.model)
must, ranked = load_counts([a.must]), load_counts([a.rank])
sets = []
for spec in a.toks:
    path, _, label = spec.partition(":")
    sets.append((label or os.path.basename(path), json.load(open(path))))

out = []
for target in a.targets:
    keep, _ = select(tokens, ttypes, merges, must, ranked, target)
    row = {"target": target, "vocab": len(keep), "gguf_bytes": size - (len(tokens) - len(keep)) * row_bytes}
    for label, seqs in sets:
        row[label] = round(100 * sum(all(t in keep for t in s) for s in seqs) / len(seqs), 2)
    out.append(row)
    print(json.dumps(row), flush=True)
