#!/usr/bin/env python3
"""audit_pii.py rules over every string of a bench v3 case, nested fields included.

    python3 audit_v3.py <cases.jsonl> [...]     exit 0 when no finding

audit_pii.scan_file only reads top-level strings and `messages`: in a v3 case it misses the
history outputs of qa cases, the questions, facts, references and the digest inputs. This
wrapper flattens the whole case and calls audit_pii.scan_text on it. Prints types and case ids
only, never a value. In `input`, a home path cut by digest() inside "/Users/user" or
"/home/user" (e.g. "/Users/us" at a cut) is read as "user". `leak_check` is skipped: its corpus
labels are a fixed schema enum, not captured data.

SPDX-License-Identifier: MIT
"""

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "finetune"))
import audit_pii  # noqa: E402

CUT_HOME = re.compile(r"/(home|Users)/(?:u|us|use)(?=\s|$)")


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def case_findings(case, names):
    rest = {k: v for k, v in case.items() if k not in ("input", "leak_check")}
    text = "\n".join(strings(rest))
    text += "\n" + CUT_HOME.sub(r"/\1/user", "\n".join(strings(case.get("input", {}))))
    return audit_pii.scan_text(text, names)


def main():
    names = audit_pii.load_names(audit_pii.DEFAULT_NAMES)
    total = collections.Counter()
    n = 0
    for p in sys.argv[1:]:
        for line in open(p):
            if not line.strip():
                continue
            case = json.loads(line)
            n += 1
            found = case_findings(case, names)
            for kind in found:
                total[kind] += 1
                print(f"{case['id']}: {kind}")
    print(f"{n} cases, {sum(total.values())} findings {dict(total)}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
