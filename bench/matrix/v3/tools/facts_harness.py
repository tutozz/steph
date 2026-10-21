#!/usr/bin/env python3
"""Bench v3 harness variant with the code-extracted facts block (L5, config facts_block = True).

    python3 facts_harness.py <generic|finetuned> <dev|test> <base_harness.json> <out.json>

The base harness is harness/<split>.json for the finetuned profile, or the output of
generic_harness.py for the generic one. Every summary row is rebuilt with the production
builder of its profile, first without facts (it must equal the base row, or the tool stops),
then with prompts.summary_messages(facts=extract_facts(...)), as narrator does when
facts_block is on. Question rows are copied unchanged: the block only touches summaries.

SPDX-License-Identifier: MIT
"""

import json
import sys

import v3lib
from steph import prompts
from steph.config import Config
from steph.digest import digest, extract_facts
from steph.textproc import compact_output

BUILDERS = {"generic": (prompts.summary_messages, Config().summary_chars),
            "finetuned": (prompts.finetuned_summary_messages, v3lib.MAX_CHARS)}


def summary_input(profile, case, lang, with_facts):
    build, chars = BUILDERS[profile]
    lines = v3lib.output_lines(case["output_raw"])
    raw = "\n".join(lines)
    out = digest(case["cmd"], raw, chars, lang) or compact_output(lines, chars)
    facts = extract_facts(case["cmd"], case["exit"], raw, lang) if with_facts else None
    return build(case["cmd"], case["exit"], case["duration_s"], out, case["nlines"], language=lang, facts=facts)


def rows(profile, split, base):
    cases = {json.loads(l)["id"]: json.loads(l) for p in sorted((v3lib.V3 / "cases" / split).glob("*.jsonl"))
             for l in open(p) if l.strip()}
    out = []
    for row in base:
        if row["kind"] != "summary":
            out.append(row)
            continue
        case = cases[row["fixture"]]
        if summary_input(profile, case, row["lang"], False) != row["messages"]:
            raise SystemExit(f"{row['id']}: le harnais de base diffère de l'entrée de production ({profile})")
        out.append({**row, "messages": summary_input(profile, case, row["lang"], True)})
    return out


def main():
    profile, split, base, out = sys.argv[1:5]
    json.dump(rows(profile, split, json.load(open(base))), open(out, "w"), ensure_ascii=False, indent=0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
