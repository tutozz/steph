# G3c : compare deux GGUF tenseur par tenseur (type et md5 des données) et liste les métadonnées qui diffèrent.
#   gguf_cmp.py <a.gguf> <b.gguf> [<a2> <b2> ...]   (PYTHONPATH=gguf-py de llama.cpp)
import sys, hashlib
from gguf import GGUFReader
def tens(p):
    r = GGUFReader(p)
    return {t.name: (int(t.tensor_type), hashlib.md5(t.data.tobytes()).hexdigest()) for t in r.tensors}, \
        {f.name: f for f in r.fields.values()}
for a, b in zip(sys.argv[1::2], sys.argv[2::2]):
    ta, fa = tens(a); tb, fb = tens(b)
    same = sum(ta[k] == tb.get(k) for k in ta)
    print(b.split("/")[-1], f"tenseurs égaux {same}/{len(ta)} (b: {len(tb)})", "métadonnées différentes :",
          sorted(k for k in set(fa) | set(fb) if k not in fa or k not in fb or bytes(fa[k].parts[-1]) != bytes(fb[k].parts[-1]))[:8])
