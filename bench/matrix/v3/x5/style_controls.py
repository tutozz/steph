#!/usr/bin/env python3
"""X5, part 2: planted controls of the spoken-style judge (judge_style_v3.py).

    python3 style_controls.py <controls.jsonl>

Each control pairs a dev reference (x) with a version carrying the same facts that is clearly
worse to hear (y): a filler preamble before the facts, a log-like line full of symbols, or the
whole sentence said twice. Expected verdict: x. Identical pairs (x == y) expect a tie.

SPDX-License-Identifier: MIT
"""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import judge_style_v3 as js  # noqa: E402

PER_KIND = 20
PREAMBLE = {"fr": "Alors, pour résumer ce que la commande a affiché dans le terminal, on peut dire que : {ref}",
            "en": "So, to sum up what the command printed in the terminal, we can say that: {ref}"}
REPEAT = {"fr": "{ref} Je répète : {ref}", "en": "{ref} Once again: {ref}"}


def log_line(ref):
    body = ref.rstrip(".").replace(" ; ", " || ").replace("; ", " || ").replace(", ", " | ").replace(" : ", " => ")
    return f"[RESULT] >> {body} <<"


WORSE = {
    "preamble": lambda ref, lang: PREAMBLE[lang].format(ref=ref[0].lower() + ref[1:]),
    "log": lambda ref, lang: log_line(ref),
    "repeat": lambda ref, lang: REPEAT[lang].format(ref=ref),
}


def load_dev_rows():
    harness = {r["id"]: r for r in json.load(open(HERE.parent / "harness" / "dev.json"))}
    cases = {}
    for f in sorted((HERE.parent / "cases" / "dev").glob("*.jsonl")):
        for line in open(f):
            if line.strip():
                c = json.loads(line)
                cases[c["id"]] = c
    return cases, harness


def rank(key):
    return hashlib.sha256(("x5-style:" + key).encode()).hexdigest()


def build():
    cases, harness = load_dev_rows()
    ids = sorted(cases, key=rank)
    out, i = [], 0
    for kind in list(WORSE) + ["identical"]:
        for n in range(PER_KIND):
            c = cases[ids[i]]
            i += 1
            lang = ("fr", "en")[n % 2]
            ref = c["reference"][lang]
            row = harness[f"{c['id']}@{lang}"]
            y = ref if kind == "identical" else WORSE[kind](ref, lang)
            out.append({"id": f"{c['id']}@{lang}#{kind}", "lang": lang, "kind": kind,
                        "context": js.context_of(row), "x": ref, "y": y,
                        "expected": "=" if kind == "identical" else "x"})
    return out


if __name__ == "__main__":
    rows = build()
    with open(sys.argv[1], "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} controls")
