#!/usr/bin/env python3
"""R2-B1 : 60 entrées du split dev v3, de longueurs variées, pour le balayage -ub.

Seules les entrées que steph envoie au modèle (reaches_model). Dix tranches de longueur
d'entrée utilisateur, trois FR et trois EN par tranche, tirage à graine fixe. Sortie triée
FR puis EN, comme une personne qui garde sa langue : le préfixe système reste en cache.
"""

import argparse
import hashlib
import json
import random


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev-json", default="bench/matrix/v3/harness/dev.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=2)
    a = ap.parse_args()

    raw = open(a.dev_json, "rb").read()
    rows = [c for c in json.loads(raw) if str(c.get("reaches_model")) == "True"]
    for c in rows:
        c["_len"] = len(c["messages"][-1]["content"])
    rng = random.Random(a.seed)
    picked = []
    for lang in ("fr", "en"):
        pool = sorted((c for c in rows if c["lang"] == lang), key=lambda c: (c["_len"], c["id"]))
        n = len(pool)
        for b in range(10):
            bin_rows = pool[b * n // 10:(b + 1) * n // 10]
            picked += rng.sample(bin_rows, 3)
    for c in picked:
        c["maxc"] = 0
        c.pop("_len")
    json.dump(picked, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"dev.json sha256 {hashlib.sha256(raw).hexdigest()} ; {len(picked)} entrées ; "
          f"qa {sum(c['kind'] == 'qa' for c in picked)}")
    print(" ".join(c["id"] for c in picked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
