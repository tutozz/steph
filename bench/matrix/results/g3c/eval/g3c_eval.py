#!/usr/bin/env python3
"""G3c TEST : G3c (t9s7 off-ple3) contre G3b off-ple3, Gemma brut et v1.0, banc v3 test aligné L5, 3 graines, même session.

    PYTHONPATH=<v3/tools>:<round-3/r3t2p3>:<finetune>:<gemma/g3b> python3 g3c_eval.py <runs/> <verdicts/> <style/> <harness/> <out.json> [<anciens runs>...]

Statistiques de g3b_eval.py (power_v3, score_production du commit archivé, lang_v3, bootstrap apparié 10 000 tirages).
Les dossiers d'anciens runs servent au contrôle de reproductibilité : réponses identiques, par graine, aux runs de G4b
(G3b off-ple3) et de G3b (brut, v1.0).

SPDX-License-Identifier: MIT
"""

import json
import sys
from pathlib import Path

import g3b_eval

g3b_eval.MODELS = ("g3c", "g3b", "gemma-raw", "v10")
g3b_eval.PAIRS = (("g3c", "g3b"), ("g3c", "gemma-raw"), ("g3c", "v10"), ("g3b", "gemma-raw"), ("g3b", "v10"))
g3b_eval.HARNESS = {"g3c": "test.generic.json", "g3b": "test.generic.json", "gemma-raw": "test.generic.json", "v10": "test.json"}
OLD = {"g3b": "g3b-ple3", "gemma-raw": "gemma-raw", "v10": "v10"}


def outs(p):
    return {r["id"]: r.get("out") for r in json.load(open(p))["rows"]}


def same_as_before(rd, olds):
    res = {}
    for m, old in OLD.items():
        for sd in g3b_eval.SEEDS:
            new = Path(rd) / f"{m}-test-b{sd}.json"
            for d in olds:
                p = Path(d) / f"{old}-test-b{sd}.json"
                if p.exists() and new.exists():
                    a, b = outs(new), outs(p)
                    res[f"{m} b{sd}"] = {"ref": str(p), "n": len(a), "identical": sum(a[k] == b.get(k) for k in a)}
                    break
    return res


if __name__ == "__main__":
    olds = sys.argv[6:]
    del sys.argv[6:]
    g3b_eval.main()
    out = Path(sys.argv[5])
    rep = json.loads(out.read_text())
    rep["reproducibility"] = same_as_before(sys.argv[1], olds)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps(rep["reproducibility"], ensure_ascii=False, indent=1))
