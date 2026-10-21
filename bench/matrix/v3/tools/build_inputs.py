#!/usr/bin/env python3
"""Regenerates the production input of bench v3 cases, in place (DESIGN.md section 5).

    python3 build_inputs.py <cases/Lxx.jsonl> [...]

Input of a question = what server._ask sends with the finetuned profile (P20): system, session
history, acknowledgement, then « (dossier actuel : {cwd})\\n{question} » (v3lib.rebuild_qa_input).
A case written before the field existed gets its `cwd` from the block headers of its old input.
Input of a summary = v3lib.rebuild_summary_input (finetuned profile, facts block L5 included).
Facts, references and history are never touched.

SPDX-License-Identifier: MIT
"""

import json
import re
import subprocess
import sys

import v3lib

HEADER = re.compile(r"^\[\d+\] (.+?) \$ ", re.M)


def steph_commit():
    return subprocess.run(["git", "log", "-1", "--format=%h", "--", "src/steph"], cwd=v3lib.REPO,
                          capture_output=True, text=True, check=True).stdout.strip()


def rebuild(case, commit):
    if case["task"] == "summary":
        builder = {**case["input"]["builder"], "steph_commit": commit}
        return {**case, "input": {"fr": v3lib.rebuild_summary_input(case, "fr"),
                                  "en": v3lib.rebuild_summary_input(case, "en"), "builder": builder}}
    if "cwd" not in case:
        user = "\n".join(m["content"] for m in case["input"]["fr"] if m["role"] == "user")
        cwds = set(HEADER.findall(user))
        if len(cwds) != 1:
            raise SystemExit(f"{case['id']}: {len(cwds)} dossiers dans l'ancienne entrée, cwd à écrire à la main")
        case = {**case, "cwd": cwds.pop()}
    builder = {**case["input"]["builder"], "steph_commit": commit}
    case["input"] = {"fr": v3lib.rebuild_qa_input(case, "fr"), "en": v3lib.rebuild_qa_input(case, "en"),
                     "builder": builder}
    return case


def main():
    commit = steph_commit()
    for path in sys.argv[1:]:
        cases = [json.loads(l) for l in open(path) if l.strip()]
        out = [rebuild(c, commit) for c in cases]
        with open(path, "w") as f:
            f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in out)
        print(f"{path}: {len(out)} entrées régénérées, dont {sum(c['task'] == 'qa' for c in out)} questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
