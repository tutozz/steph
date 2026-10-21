#!/usr/bin/env python3
"""Token lengths of corpus rows and bench inputs under the Gemma 4 chat template (G3 foundation).

    python3 token_stats.py --tokenizer <gemma dir> --corpus data/final-x4/*.jsonl --harness dev.generic.json

Corpus rows are counted twice: as written (short training prompts) and rewritten to the
production generic prompts (gemma_format.to_generic). Harness files hold production inputs
without an answer. Only counts are printed, never corpus text.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gemma_format import to_generic
from transformers import AutoTokenizer


def pct(values: list[int]) -> dict:
    v = sorted(values)
    if not v:
        return {}
    q = lambda p: v[min(len(v) - 1, int(p * len(v)))]  # noqa: E731
    return {"n": len(v), "p50": q(0.5), "p90": q(0.9), "p95": q(0.95), "p99": q(0.99), "max": v[-1],
            "over_1024": sum(x > 1024 for x in v), "over_1536": sum(x > 1536 for x in v),
            "over_2048": sum(x > 2048 for x in v), "over_4096": sum(x > 4096 for x in v)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--corpus", nargs="*", default=[])
    ap.add_argument("--harness", nargs="*", default=[])
    a = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(a.tokenizer)

    def count(messages: list[dict], gen: bool) -> int:
        text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=gen, enable_thinking=False)
        return len(tok(text, add_special_tokens=False)["input_ids"])

    report: dict = {"corpus": {}, "harness": {}}
    everything = {"train_prompt": [], "generic": [], "answer": []}
    for path in a.corpus:
        rows = [json.loads(line)["messages"] for line in open(path, encoding="utf-8") if line.strip()]
        full, generic, answer, unknown = [], [], [], 0
        for m in rows:
            full.append(count(m, False))
            g, known = to_generic(m)
            unknown += not known
            generic.append(count(g, False))
            answer.append(count(m, False) - count(m[:-1], True))
        report["corpus"][Path(path).name] = {"train_prompt": pct(full), "generic": pct(generic),
                                             "answer": pct(answer), "unknown_system": unknown}
        everything["train_prompt"] += full; everything["generic"] += generic; everything["answer"] += answer
    report["corpus_all"] = {k: pct(v) for k, v in everything.items()}
    for path in a.harness:
        rows = json.load(open(path, encoding="utf-8"))
        by_kind: dict[str, list[int]] = {}
        for r in rows:
            by_kind.setdefault(r.get("kind", "?"), []).append(count(r["messages"], True))
        report["harness"][Path(path).name] = {k: pct(v) for k, v in sorted(by_kind.items())}
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
