#!/usr/bin/env python3
"""R1 : contrôle par source sur la validation du mix (jamais entraînée) : inventions au juge A7,
bonne langue et sorties vides, pour chaque fonctionnalité (résumé, détail, début, progression,
questions) en français et en anglais.

    python3 feature_check_r1.py <dossier du mix> <gen.jsonl> <verdicts.jsonl>

gen.jsonl et verdicts.jsonl viennent de gen_outputs.py et judge_outputs.py sur ce dossier. N'imprime
que des comptes, jamais de texte du corpus.

SPDX-License-Identifier: MIT
"""

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from judge_outputs import key, norm  # noqa: E402
from lang_rate import classify, profiles  # noqa: E402


def main():
    data, gen, verdicts = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    val = [json.loads(line) for line in open(data / "val.jsonl")]
    final = {v["key"]: v["final"] for v in map(json.loads, open(verdicts))}
    profs = profiles()
    stats = collections.defaultdict(collections.Counter)
    for g in map(json.loads, open(gen)):
        if g["split"] != "val":
            continue
        row = val[g["idx"]]
        src, msgs = row["source"], row["messages"]
        lang = "en" if src.endswith("_en") or src == "en_summary" else "fr"
        st = stats[src]
        st["n"] += 1
        if not g["out"].strip():
            st["empty"] += 1
            continue
        st["right_lang"] += classify(g["out"], profs) == lang
        if norm(g["out"]) == norm(msgs[2]["content"]):
            st["same_as_label"] += 1
            continue
        st[final.get(key(msgs[1]["content"], g["out"]), "not_judged")] += 1
    out = {}
    for src, st in sorted(stats.items()):
        n = st["n"]
        out[src] = {**st, "invention_pct": round(100 * st["invention"] / n, 1),
                    "right_lang_pct": round(100 * st["right_lang"] / max(1, n - st["empty"]), 1)}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
