#!/usr/bin/env python3
"""R2 : tirage des paires jugées à l'oral (judge_style_v3.py), comme la démonstration X5.

    python3 style_sample.py <runA.json> <runB.json> <n> <outA.json> <outB.json>

Garde les lignes où les deux réponses nettoyées diffèrent, les ordonne par sha256("r2-style:" + id)
et écrit les n premières de chaque run : judge_style_v3.py run ne jugera que celles-là.

SPDX-License-Identifier: MIT
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from score import clean  # noqa: E402


def pick(rows_a, rows_b, n):
    a = {r["id"]: r for r in rows_a if r.get("out") is not None}
    b = {r["id"]: r for r in rows_b if r.get("out") is not None}
    diff = [i for i in set(a) & set(b) if clean(a[i]["out"]) != clean(b[i]["out"])]
    return sorted(diff, key=lambda i: hashlib.sha256(("r2-style:" + i).encode()).hexdigest())[:n], len(diff)


def main():
    pa, pb, n, oa, ob = sys.argv[1:]
    ra, rb = json.load(open(pa)), json.load(open(pb))
    ids, ndiff = pick(ra["rows"], rb["rows"], int(n))
    keep = set(ids)
    for src, out in ((ra, oa), (rb, ob)):
        json.dump({**src, "rows": [r for r in src["rows"] if r["id"] in keep]}, open(out, "w"), ensure_ascii=False)
    print(json.dumps({"differ": ndiff, "picked": len(ids),
                      "fr": sum(i.endswith("@fr") for i in ids), "en": sum(i.endswith("@en") for i in ids)}))


if __name__ == "__main__":
    main()
