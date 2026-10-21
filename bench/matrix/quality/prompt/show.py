"""Détail par cas tune d'un résultat : score nettoyé et sortie. python3 show.py <résultat.json>"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))
from score import HOLDOUT, clean, score_case  # noqa: E402

for p in sys.argv[1:]:
    print("#", Path(p).stem)
    for r in json.load(open(p))["rows"]:
        if r["fixture"] in HOLDOUT or r.get("out") is None:
            continue
        s = score_case(r["fixture"], r["kind"], clean(r["out"]))
        print(f"{s:4.2f} {r['fixture']:6} {clean(r['out'])[:150]}")
