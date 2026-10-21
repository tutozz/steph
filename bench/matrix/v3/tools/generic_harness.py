#!/usr/bin/env python3
"""Bench v3 harness in the production format of the generic profile, for raw models (X3).

    python3 generic_harness.py <dev|test> <out.json>

Same rows, ids, reaches_model and production sampling (payload) as harness/<split>.json (finetuned profile, B3). Only the
messages change, as narrator sends them with llm_profile = generic: summary_messages()
(SUMMARY_SYSTEM) over digest() capped at cfg.summary_chars, with the facts block (L5) when
cfg.facts_block is on; questions through
Narrator.qa_messages() with the history budget cfg.qa_budget_chars instead of the finetuned
8 000 characters, then the question of server._ask.

SPDX-License-Identifier: MIT
"""

import json
import sys

import v3lib
from steph import prompts
from steph.config import Config
from steph.digest import digest
from steph.textproc import compact_output


def summary_input(case, lang):
    chars = Config().summary_chars
    lines = v3lib.output_lines(case["output_raw"])
    out = digest(case["cmd"], "\n".join(lines), chars, lang) or compact_output(lines, chars)
    return prompts.summary_messages(case["cmd"], case["exit"], case["duration_s"], out, case["nlines"], language=lang,
                                    facts=v3lib.production_facts(case, lang))


def qa_input(case, lang):
    from qa_corpus import QUESTION_PREFIX
    from steph.narrator import Narrator
    from steph.session import Session

    s = Session()
    nar = Narrator(Config(language=lang, llm_profile="generic", qa_block_chars=v3lib.QA_BLOCK_CHARS), s, None, None)
    for h in case["history"]:
        s.cwd = case["cwd"]
        c = s.start(h["cmd"])
        out = h["output_raw"]
        if out:
            c.feed((out if out.endswith("\n") else out + "\n").encode())
        c.start, c.end, c.exit = 1e9, 1e9 + h["duration_s"], h["exit"]
        nar.qa_messages()
    s.cwd = case["cwd"]
    return nar.qa_messages() + [{"role": "user",
                                 "content": QUESTION_PREFIX.format(cwd=case["cwd"], question=case["question"][lang])}]


def rows(split):
    cases = sorted((json.loads(l) for p in sorted((v3lib.V3 / "cases" / split).glob("*.jsonl"))
                    for l in open(p) if l.strip()), key=lambda c: c["id"])
    # reaches_model recopié du harnais figé : resolve() évolue (aides L1, L2), l'empreinte du harnais ne doit pas bouger
    frozen = {h["id"]: h["reaches_model"] for h in json.load(open(v3lib.V3 / "harness" / f"{split}.json"))}
    out = []
    for c in cases:
        for lang in ("fr", "en"):
            msgs = summary_input(c, lang) if c["task"] == "summary" else qa_input(c, lang)
            out.append({"id": f"{c['id']}@{lang}", "fixture": c["id"],
                        "cmd": c["cmd"] if c["task"] == "summary" else c["question"][lang],
                        "kind": c["task"], "maxc": 0, "messages": msgs, "lang": lang,
                        "family": c["family"], "reaches_model": frozen[f"{c['id']}@{lang}"],
                        "payload": v3lib.production_payload(c["task"])})
    return out


def main():
    split, out = sys.argv[1], sys.argv[2]
    json.dump(rows(split), open(out, "w"), ensure_ascii=False, indent=0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
