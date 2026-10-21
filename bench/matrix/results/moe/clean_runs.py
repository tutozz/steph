#!/usr/bin/env python3
"""G6 : applique aux sorties de bench_run le nettoyage de production du narrateur
(`narrator._stream_clean` : balises <think>, gras et accents graves retirés), comme steph le fait
avant de parler. Les sorties brutes restent dans <runs>, les nettoyées vont dans <out>.

    PYTHONPATH=src python3 clean_runs.py <runs dir> <out dir>

SPDX-License-Identifier: MIT
"""

import json
import sys
from pathlib import Path

from steph.narrator import _stream_clean


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.glob("*-test-b*.json")):
        d = json.load(open(p))
        changed = 0
        for r in d["rows"]:
            if r.get("out"):
                clean = "".join(_stream_clean(iter([r["out"]]))).strip()
                changed += clean != r["out"]
                r["out"] = clean
        json.dump(d, open(dst / p.name, "w"), ensure_ascii=False, indent=1)
        print(p.name, "sorties modifiées :", changed)


if __name__ == "__main__":
    main()
