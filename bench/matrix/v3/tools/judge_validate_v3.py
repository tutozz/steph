#!/usr/bin/env python3
"""Revalidates the A7 invention judge for bench v3: the 6 French controls C1-C6, plus 6 English
controls built on real bench v3 dev contexts (same design: 3 faithful, 3 planted inventions).

    python3 judge_validate_v3.py build <controls.json>          # on the Mac, from cases/dev
    PYTHONPATH=<A7 judge_lib dir> python3 judge_validate_v3.py run <controls.json> <out.json>

judge_lib_a7.py and judge_validate.py stay untouched: `run` imports call_judge from the remote
copy of the A7 judge_lib (prompt in French), `build` copies C1-C6 from judge_validate.py.
Exit 0 only if every control is right on both passes A and B, in each language.

SPDX-License-Identifier: MIT
"""

import ast
import json
import sys
from pathlib import Path

V3 = Path(__file__).resolve().parents[1]

# (id, dev case, expected, phrase) - mirrors C1-C6: faithful figures, faithful file:line,
# faithful count; then a wrong figure, a wrong line, a wrong status with invented failures.
ENGLISH_CONTROLS = [
    ("V3E1-faithful-memory", "v3-disk-memory-0023", "ok", "13Gi available of 15Gi, 2.0Gi used, swap empty."),
    ("V3E2-faithful-error-line", "v3-build-native-0032", "ok",
     "Failed. src/tls.c line 1: header openssl/ssl.h not found."),
    ("V3E3-faithful-tests", "v3-tests-0025", "ok", "All 7 tests passed in 2 suites."),
    ("V3E4-invented-figure", "v3-disk-memory-0023", "invention", "15Gi total, only 9Gi available."),
    ("V3E5-invented-line", "v3-build-native-0032", "invention",
     "Failed. src/tls.c line 12: header openssl/ssl.h not found."),
    ("V3E6-invented-status", "v3-tests-0025", "invention", "Failed. 2 of 7 tests failed in store.test.js."),
]


def french_controls():
    """C1-C6 read from judge_validate.py without importing it (it imports judge_lib)."""
    src = (V3.parents[0] / "finetune" / "judge_validate.py").read_text()
    tree = ast.parse(src)
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.startswith("CTX_") and not name.endswith("_EN"):
                consts[name] = ast.literal_eval(node.value)
            if name == "CONTROL_CASES":
                cases = []
                for elt in node.value.elts:
                    d = {k.value: v for k, v in zip(elt.keys, elt.values)}
                    cases.append({"id": d["id"].value, "lang": "fr", "context": consts[d["context"].id],
                                  "phrase": d["phrase"].value, "expected": d["expected"].value})
                return cases
    raise SystemExit("CONTROL_CASES not found in judge_validate.py")


def build(out):
    dev = {}
    for p in (V3 / "cases" / "dev").glob("*.jsonl"):
        for line in open(p):
            c = json.loads(line)
            dev[c["id"]] = c
    cases = french_controls()
    for cid, case_id, expected, phrase in ENGLISH_CONTROLS:
        user = [m for m in dev[case_id]["input"]["en"] if m["role"] == "user"][0]["content"]
        cases.append({"id": cid, "lang": "en", "source": case_id, "context": user, "phrase": phrase,
                      "expected": expected})
    json.dump(cases, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"{len(cases)} controls written to {out}")


def run(path, out):
    from judge_lib import call_judge

    cases = json.load(open(path))
    rows = []
    for c in cases:
        verdicts = {}
        for pass_id in ("A", "B"):
            r = call_judge(c["context"], c["phrase"], pass_id=pass_id)
            verdicts[pass_id] = {"verdict": r["verdict"], "inventions": r["inventions"]}
        ok = all(v["verdict"] == c["expected"] for v in verdicts.values())
        rows.append({"id": c["id"], "lang": c["lang"], "expected": c["expected"], "phrase": c["phrase"],
                     "passes": verdicts, "correct": ok})
        print(f"[{'OK' if ok else 'FAIL'}] {c['lang']} {c['id']}: attendu={c['expected']} "
              f"A={verdicts['A']['verdict']} B={verdicts['B']['verdict']} {verdicts['A']['inventions']}")
    summary = {lang: {p: f"{sum(r['passes'][p]['verdict'] == r['expected'] for r in rows if r['lang'] == lang)}"
                         f"/{sum(r['lang'] == lang for r in rows)}" for p in ("A", "B")}
               for lang in ("fr", "en")}
    print(json.dumps(summary))
    json.dump({"summary": summary, "rows": rows}, open(out, "w"), ensure_ascii=False, indent=1)
    return 0 if all(r["correct"] for r in rows) else 1


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build(sys.argv[2])
    else:
        raise SystemExit(run(sys.argv[2], sys.argv[3]))
