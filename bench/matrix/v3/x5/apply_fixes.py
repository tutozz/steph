#!/usr/bin/env python3
"""X5: applies the fact fixes of fact_fixes.json to the lots (cases/L*.jsonl), facts only.

    python3 apply_fixes.py fact_fixes.json

fact_fixes.json: {case_id: {"need"|"never": {fact_id: {"fr": [alt, ...], "en": [alt, ...]}},
                            "set": {"need"|"never": {fact_id: {"fr": [...], "en": [...]}}},
                            "add_never": [{"id", "desc", "fr": [...], "en": [...]}]}}.
An alternative is appended to the fact's first pattern with `|` unless already there; `set`
replaces a fact's patterns (a pattern that matched too much); a new never is added unless its
id exists. The output, the input and the reference are never touched:
the script refuses a case whose other fields change. Rerun is a no-op.

SPDX-License-Identifier: MIT
"""

import copy
import json
import sys
from pathlib import Path

LOTS = Path(__file__).resolve().parents[1] / "cases"


def apply(case, fix):
    before = copy.deepcopy(case)
    for kind in ("need", "never"):
        for fact_id, langs in fix.get(kind, {}).items():
            fact = next(f for f in case["facts"][kind] if f["id"] == fact_id)
            for lang, alts in langs.items():
                for alt in alts:
                    if f"|{alt}|" not in f"|{fact[lang][0]}|":
                        fact[lang][0] += "|" + alt
    for kind, facts in fix.get("set", {}).items():
        for fact_id, langs in facts.items():
            fact = next(f for f in case["facts"][kind] if f["id"] == fact_id)
            fact.update(langs)
    for nv in fix.get("add_never", []):
        if all(f["id"] != nv["id"] for f in case["facts"]["never"]):
            case["facts"]["never"].append(nv)
    assert {k: v for k, v in case.items() if k != "facts"} == {k: v for k, v in before.items() if k != "facts"}
    return case != before


def main():
    fixes = json.load(open(sys.argv[1]))
    changed = set()
    for lot in sorted(LOTS.glob("L*.jsonl")):
        lines = open(lot).read().split("\n")
        out = []
        for line in lines:
            if line.strip():
                c = json.loads(line)
                if c["id"] in fixes and apply(c, fixes[c["id"]]):
                    changed.add(c["id"])
                    line = json.dumps(c, ensure_ascii=False)
            out.append(line)
        open(lot, "w").write("\n".join(out))
    missing = set(fixes) - changed
    print(f"{len(changed)} cases changed; unchanged or absent: {sorted(missing)}")


if __name__ == "__main__":
    main()
