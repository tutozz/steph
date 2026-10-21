#!/usr/bin/env python3
"""Right-language rate of bench v3 answers (L2p trigram method of pref/lang_rate.py): answers to
`<case>@fr` rows should be French, `<case>@en` rows English.

    python3 lang_v3.py <run.json> [...]

SPDX-License-Identifier: MIT
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pref"))
from lang_rate import classify, profiles  # noqa: E402


def main():
    profs = profiles()
    for path in sys.argv[1:]:
        rows = json.load(open(path))["rows"]
        res = {}
        for lang in ("fr", "en"):
            outs = [r["out"] for r in rows if r["id"].endswith("@" + lang) and (r.get("out") or "").strip()]
            ok = sum(classify(o, profs) == lang for o in outs)
            res[lang] = {"n": len(outs), "right": round(100 * ok / max(1, len(outs)), 1)}
        print(json.dumps({"file": Path(path).name, **res}))


if __name__ == "__main__":
    main()
