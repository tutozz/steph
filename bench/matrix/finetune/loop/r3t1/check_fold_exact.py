import sys, numpy as np
sys.path.insert(0, "/root/steph-ft/loop/r3t1/src/gguf-py")
from gguf import GGUFReader
O = {"Q4_K": (144, (0, 2)), "Q6_K": (210, (208,))}
a = GGUFReader("/root/steph-ft/loop/r3t1/dense.gguf"); b = GGUFReader(sys.argv[1])
bt = {t.name: t for t in b.tensors}
for t in a.tensors:
    u = bt[t.name]
    if u.tensor_type != t.tensor_type:
        print(t.name, t.tensor_type.name, "->", u.tensor_type.name); continue
    if np.array_equal(np.asarray(t.data).view(np.uint8), np.asarray(u.data).view(np.uint8)): continue
    size, offs = O[t.tensor_type.name]
    x = np.asarray(t.data).reshape(-1).view(np.uint8).reshape(-1, size); y = np.asarray(u.data).reshape(-1).view(np.uint8).reshape(-1, size)
    q = np.ones(size, bool)
    for o in offs: q[o:o+2] = False
    qs_same = np.array_equal(x[:, q], y[:, q])
    ratios = []; inexact = 0
    for o in offs:
        vx = x[:, o:o+2].copy().view(np.float16).reshape(-1).astype(np.float64); vy = y[:, o:o+2].copy().view(np.float16).reshape(-1).astype(np.float64)
        nz = vx != 0
        r = vy[nz] / vx[nz]; ratios.append(np.median(r)); inexact += int(np.sum(np.abs(r - np.median(r)) > 0))
    print(t.name, t.tensor_type.name, "quants identiques" if qs_same else "QUANTS CHANGENT", "ratio", ratios, "échelles inexactes", inexact)
for k in ("granite.residual_scale", "granite.embedding_scale", "granite.attention.scale", "granite.logit_scale"):
    if k in a.fields: print(k, a.fields[k].parts[-1][0], b.fields[k].parts[-1][0])
