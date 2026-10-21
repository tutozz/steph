#!/usr/bin/env python3
"""Check that benchmark cases do not overlap a training corpus.

    python3 benchmark/tools/check_contamination.py --corpus 'train/*.jsonl' [--split test] [--json report.json]

Corpus files are JSON Lines; every string field of every record is read (output, cmd,
messages content...). Plain text files are read as a whole. For each case output:

- exact: the whole output, whitespace-normalized, equals a corpus text;
- lines: share of the case's non-trivial lines (20+ characters) found verbatim in the corpus;
- near_lines: same after masking digits and hex runs (catches regenerated templates);
- ngrams: share of the case's word 8-grams found in the corpus.

A case is CONTAMINATED when exact, lines >= 0.5 or ngrams >= 0.5; SUSPECT when
near_lines >= 0.8. Exit code 1 if any case is contaminated. The report prints ratios only,
never corpus text.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
REPO = BENCH.parent
DEFAULT_CORPUS = [str(REPO / "bench/matrix/finetune/corpus/*.jsonl"),
                  str(REPO / "bench/matrix/finetune/snapshot-*/*.jsonl"),
                  str(REPO / "bench/matrix/finetune/snapshot-*/**/*.jsonl")]
N = 8
MIN_LINE = 20


def norm_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().lower()


def mask(line: str) -> str:
    return re.sub(r"\d+", "0", re.sub(r"\b[0-9a-f]{6,}\b", "h", line))


def h(text: str) -> bytes:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()


def ngrams(text: str):
    words = re.findall(r"\S+", text.lower())
    for i in range(len(words) - N + 1):
        yield h(" ".join(words[i:i + N]))


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def corpus_texts(paths: list):
    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        if path.endswith(".jsonl"):
            for line in text.splitlines():
                try:
                    yield from strings(json.loads(line))
                except json.JSONDecodeError:
                    yield line
        else:
            yield text


class Index:
    def __init__(self, paths: list):
        self.full, self.lines, self.near, self.grams, self.records = set(), set(), set(), set(), 0
        for text in corpus_texts(paths):
            self.records += 1
            self.full.add(h(norm_line(text)))
            for line in text.splitlines():
                line = norm_line(line)
                if len(line) >= MIN_LINE:
                    self.lines.add(h(line))
                    self.near.add(h(mask(line)))
            self.grams.update(ngrams(text))


def case_text(case: dict) -> str:
    if case["task"] == "qa":
        return "\n".join(e["output"] for e in case["history"])
    return case["output"]


def measure(text: str, index: Index) -> dict:
    lines = [norm_line(l) for l in text.splitlines()]
    lines = [l for l in lines if len(l) >= MIN_LINE]
    grams = list(ngrams(text))

    def ratio(hits, total):
        return round(hits / total, 3) if total else 0.0

    return {
        "exact": h(norm_line(text)) in index.full,
        "lines": ratio(sum(h(l) in index.lines for l in lines), len(lines)),
        "near_lines": ratio(sum(h(mask(l)) in index.near for l in lines), len(lines)),
        "ngrams": ratio(sum(g in index.grams for g in grams), len(grams)),
    }


def verdict(m: dict) -> str:
    if m["exact"] or m["lines"] >= 0.5 or m["ngrams"] >= 0.5:
        return "CONTAMINATED"
    if m["near_lines"] >= 0.8:
        return "SUSPECT"
    return "clean"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--corpus", nargs="*", default=DEFAULT_CORPUS, help="glob patterns of corpus files")
    ap.add_argument("--data", default=str(BENCH / "data" / "v1"))
    ap.add_argument("--split", default="test", choices=["dev", "test", "all"])
    ap.add_argument("--json", default="", help="write the full report here")
    a = ap.parse_args()

    paths = sorted({p for pattern in a.corpus for p in glob.glob(pattern, recursive=True) if Path(p).is_file()})
    if not paths:
        print("no corpus file found", file=sys.stderr)
        return 2
    index = Index(paths)
    splits = ["dev", "test"] if a.split == "all" else [a.split]
    report, seen = [], {}
    for path in sorted(Path(a.data).glob("*/*.jsonl")):
        if path.stem not in splits:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            case = json.loads(line)
            text = case_text(case)
            key = h(text)
            m = seen.get(key) or measure(text, index)
            seen[key] = m
            report.append({"id": case["id"], "lang": case["lang"], "split": case["split"], **m, "verdict": verdict(m)})

    worst = sorted(report, key=lambda r: (-r["ngrams"], -r["lines"]))
    counts = {v: sum(r["verdict"] == v for r in report) for v in ("clean", "SUSPECT", "CONTAMINATED")}
    print(f"corpus: {len(paths)} files, {index.records} texts, {len(index.lines)} distinct lines, "
          f"{len(index.grams)} distinct {N}-grams")
    print(f"cases checked: {len(report)} ({', '.join(splits)}); {counts}")
    print(f"{'case':<40} {'lang':<4} {'exact':<6} {'lines':>6} {'near':>6} {'ngrams':>7}  verdict")
    for r in worst[:15]:
        print(f"{r['id']:<40} {r['lang']:<4} {str(r['exact']):<6} {r['lines']:>6} {r['near_lines']:>6} "
              f"{r['ngrams']:>7}  {r['verdict']}")
    if a.json:
        Path(a.json).write_text(json.dumps({"corpus_files": len(paths), "corpus_texts": index.records,
                                            "summary": counts, "cases": report}, indent=1) + "\n")
    return 1 if counts["CONTAMINATED"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
