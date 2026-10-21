#!/usr/bin/env python3
"""Checks bench v3 cases: schema, production input, facts and references (DESIGN.md sections 4-5).

    python3 validate.py <cases.jsonl> [...]      exit 0 when every case passes

Per case: JSON Schema 2020-12; summary input identical to the one rebuilt from src/steph at HEAD;
every fact regex compiles; the reference scores 100 % in FR and EN within max_words; qa input
carries the question. Prints one line per error, then a count.

SPDX-License-Identifier: MIT
"""

import json
import re
import sys

import jsonschema

import score_v3
import v3lib

SCHEMA = json.load(open(v3lib.V3 / "schema.json"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def case_errors(case):
    errs = [f"schema: {e.message[:160]}" for e in VALIDATOR.iter_errors(case)]
    if errs:
        return errs
    for kind in ("need", "never"):
        for f in case["facts"][kind]:
            for lang in ("fr", "en"):
                for p in f[lang]:
                    try:
                        re.compile(p)
                    except re.error as e:
                        errs.append(f"regex {kind}.{f['id']}.{lang}: {e}")
    if errs:
        return errs
    for lang in ("fr", "en"):
        ref = case["reference"][lang]
        s = score_v3.score_answer(case, lang, ref)
        if s < 1.0:
            errs.append(f"reference {lang} scores {s:.2f}")
        if case["task"] == "summary" and v3lib.rebuild_summary_input(case, lang) != case["input"][lang]:
            errs.append(f"input {lang} differs from src/steph at HEAD")
        if case["task"] == "qa":
            if v3lib.rebuild_qa_input(case, lang) != case["input"][lang]:
                errs.append(f"input {lang} differs from src/steph at HEAD")
            user = "\n".join(m["content"] for m in case["input"][lang] if m["role"] == "user")
            if case["question"][lang] not in user:
                errs.append(f"input {lang} lacks the question")
            if any(h["cmd"] not in user for h in case["history"][-3:]):
                errs.append(f"input {lang} lacks one of the last history commands")
    return errs


def main():
    cases = [json.loads(l) for p in sys.argv[1:] for l in open(p) if l.strip()]
    n_err = 0
    for c in cases:
        for e in case_errors(c):
            n_err += 1
            print(f"{c.get('id')}: {e}")
    print(f"{len(cases)} cases, {n_err} errors")
    return 1 if n_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
