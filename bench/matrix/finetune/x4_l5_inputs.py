"""L5: rewrites the summary inputs of data/final-x4 with the code-extracted facts block, on the machine
that holds the corpus. Labels, system turns and every other field are kept byte for byte.

    python3 x4_l5_inputs.py --final data/final-x4 --raw data/corpus/*.jsonl data/snapshot-1/clean/*.jsonl \\
        --out data/final-x4-l5

- summary files (SUMMARY_FILES, ".en" in the name for English): each row is matched to its raw record
  (compose_k3.match_raw, facts block ignored), then the block of extract_facts(raw output) is put where
  prompts.summary_messages puts it, right before the output; the labeled output part is not rebuilt,
  so the label still reads the input it was written for;
- a row with no raw record is copied unchanged and counted as unmatched;
- other files (detail, progress, flux) are copied unchanged: the block only exists in summaries;
- README.txt gains a note, SHA256SUMS is rewritten for every .jsonl.
Written files hold corpus text and stay on the machine; only counts are printed.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compose_k3 import OUTPUT_MARKER, match_raw, raw_index  # noqa: E402
from label import strip_facts_block  # noqa: E402

from steph.digest import extract_facts  # noqa: E402
from steph.prompts import facts_block  # noqa: E402

SUMMARY_FILES = {"macos", "linux-low", "linux-dev", "snapshot-linux-dev", "snapshot-linux-low",
                 "macos.en", "linux-low.en"}
README_NOTE = ("\nL5 : entrées des résumés réécrites par x4_l5_inputs.py avec le bloc de faits extraits en code "
               "(digest.extract_facts), comme narrator.py depuis 20cfa0d ; étiquettes inchangées.\n")


def lang_of(stem: str) -> str:
    return "en" if stem.endswith(".en") else "fr"


def with_facts(user: str, rec: dict, lang: str) -> str:
    bare = strip_facts_block(user, lang)
    marker = OUTPUT_MARKER[lang]
    at = bare.index(marker)
    return bare[:at] + facts_block(extract_facts(rec["cmd"], rec["exit"], rec["output"], lang), lang) + bare[at:]


def rewrite(rows: list[dict], index: dict[str, list[dict]], lang: str) -> tuple[list[dict], dict]:
    counts = {"rows": len(rows), "with_facts": 0, "no_facts": 0, "unmatched": 0}
    out = []
    for row in rows:
        user = row["messages"][1]["content"]
        rec = match_raw(user, index, lang)
        if rec is None:
            counts["unmatched"] += 1
            out.append(row)
            continue
        new_user = with_facts(user, rec, lang)
        counts["with_facts" if new_user != strip_facts_block(user, lang) else "no_facts"] += 1
        msgs = [row["messages"][0], {**row["messages"][1], "content": new_user}, *row["messages"][2:]]
        out.append({**row, "messages": msgs})
    return out, counts


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", type=Path, required=True, help="data/final-x4")
    ap.add_argument("--raw", type=Path, nargs="+", required=True, help="raw corpus the rows were labeled from")
    ap.add_argument("--out", type=Path, required=True, help="data/final-x4-l5, created")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    indexes = {lang: raw_index(args.raw, lang) for lang in ("fr", "en")}
    report: dict = {"files": {}}
    for path in sorted(args.final.glob("*.jsonl")):
        stem = path.name[:-len(".jsonl")]
        if stem not in SUMMARY_FILES:
            shutil.copyfile(path, args.out / path.name)
            report["files"][path.name] = {"rows": len(read_jsonl(path)), "copied": 1}
            continue
        lang = lang_of(stem)
        rows, counts = rewrite(read_jsonl(path), indexes[lang], lang)
        with (args.out / path.name).open("w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        report["files"][path.name] = counts
    readme = args.final / "README.txt"
    note = readme.read_text(encoding="utf-8") if readme.exists() else ""
    (args.out / "README.txt").write_text(note + (README_NOTE if README_NOTE not in note else ""), encoding="utf-8")
    sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(args.out.glob("*.jsonl"))]
    (args.out / "SHA256SUMS").write_text("".join(sums))
    print(json.dumps(report, ensure_ascii=False))
    return report


if __name__ == "__main__":
    main()
