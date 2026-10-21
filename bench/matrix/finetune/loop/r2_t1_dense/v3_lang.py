#!/usr/bin/env python3
"""Right-language rate of bench v3 answers, per prompt language (row id suffix @fr / @en).

    python3 v3_lang.py <bench_run result> [...]

Uses the L2p trigram classifier of pref/lang_rate.py; empty answers are skipped.

SPDX-License-Identifier: MIT
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pref"))
from lang_rate import classify, profiles  # noqa: E402


def main() -> None:
    profs = profiles()
    for path in sys.argv[1:]:
        rows = json.load(open(path))["rows"]
        out = {}
        for lang in ("fr", "en"):
            answers = [r.get("out") or "" for r in rows if r["id"].endswith("@" + lang)]
            answers = [a for a in answers if a.strip()]
            right = sum(classify(a, profs) == lang for a in answers)
            out[lang] = {"n": len(answers), "right_lang_pct": round(100 * right / len(answers), 1) if answers else None}
        print(json.dumps({"file": Path(path).name, **out}))


if __name__ == "__main__":
    main()
