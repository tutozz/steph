"""Rewrite a composed fine-tuning set into the input format steph sends today (P15).

    python3 rebuild_p15.py --mix mix-judged --raw corpus/*.jsonl snapshot-1/clean/*.jsonl \\
        --qa final/qa_train.jsonl --max-chars 587 --out mix-p15

Summary rows come from compose_train.py (judge rejects and bench overlap already removed).
Each one is matched back to its raw record by the header of the old user message (command,
status, duration, line count), its user message is rebuilt with today's digest() under the
token-capped budget, its system prompt becomes TRAIN_SYSTEM, and the leading « Succès. » /
« Échec. » of the label goes away: steph says the status in code since P9.

Labels were written on longer inputs. A label that loses a clause under
steph.grounding.ground() against its new input is dropped: training on it would teach the
model to cite a fact it cannot see. Question rows keep their history and are filtered the
same way. Only counts are printed, never corpus text.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from label import TRAIN_SYSTEM, build_messages, strip_facts_block  # noqa: E402

# ground() normalizes its output, so a clause-level check reads the same helpers it uses
from steph.grounding import _METADATA_NUMBER_RE, _fold, _is_grounded, _numbers_in, _split_segments  # noqa: E402

_LEADING_STATUS = re.compile(r"^\s*(?:Succès|Échec)(?:\s*[,(]?\s*code\s*\d+\)?)?\s*[.,:;!]?(?:\s+|$)")
_OUTPUT_MARKER = "Sortie :\n"


def strip_status(label: str) -> str:
    return _LEADING_STATUS.sub("", label, count=1).strip()


def header_key(user: str) -> str:
    return strip_facts_block(user).split(_OUTPUT_MARKER, 1)[0]


def _output_of(user: str) -> str:
    return user.split(_OUTPUT_MARKER, 1)[-1]


def match_raw(user: str, index: dict[str, list[dict]]) -> dict | None:
    candidates = index.get(header_key(user), [])
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    old_output = _output_of(user)
    for rec in candidates:
        if _output_of(build_messages(rec, 1500)[1]["content"]) == old_output:
            return rec
    # the digest changed since labeling: fall back to the raw output sharing most words
    words = set(re.findall(r"\S{4,}", old_output))
    scored = sorted(((len(words & set(re.findall(r"\S{4,}", rec["output"]))), i) for i, rec in enumerate(candidates)),
                    reverse=True)
    best, runner_up = scored[0], scored[1]
    if best[0] > runner_up[0] or candidates[best[1]]["output"] == candidates[runner_up[1]]["output"]:
        return candidates[best[1]]
    return None


def loses_fact(user: str, label: str) -> bool:
    """True when ground() would cut at least one clause of `label` given `user` as input."""
    numbers = _numbers_in(_METADATA_NUMBER_RE.sub(" ", user))
    folded = _fold(user)
    return not all(_is_grounded(segment, numbers, folded) for segment, _ in _split_segments(label))


def rebuild_row(row: dict, rec: dict, max_chars: int) -> dict:
    user = build_messages(rec, max_chars)[1]
    return {"messages": [{"role": "system", "content": TRAIN_SYSTEM}, user,
                         {"role": "assistant", "content": strip_status(row["messages"][-1]["content"])}]}


def _is_val(text: str) -> bool:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % 20 == 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mix", type=Path, required=True, help="dossier train.jsonl/val.jsonl de compose_train.py")
    ap.add_argument("--raw", type=Path, nargs="+", required=True)
    ap.add_argument("--qa", type=Path)
    ap.add_argument("--max-chars", dest="max_chars", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    index: dict[str, list[dict]] = {}
    for path in args.raw:
        for line in path.open():
            rec = json.loads(line)
            index.setdefault(header_key(build_messages(rec, 1500)[1]["content"]), []).append(rec)

    stats = collections.Counter()
    split = {"train": [], "val": []}
    for name in split:
        for line in (args.mix / f"{name}.jsonl").open():
            row = json.loads(line)
            rec = match_raw(row["messages"][1]["content"], index)
            if rec is None:
                stats["summary_unmatched"] += 1
                continue
            new = rebuild_row(row, rec, args.max_chars)
            label = new["messages"][2]["content"]
            if not label:
                stats["summary_status_only"] += 1
                continue
            if loses_fact(new["messages"][1]["content"], label):
                stats["summary_lost_fact"] += 1
                if not loses_fact(row["messages"][1]["content"], label):
                    stats["summary_lost_fact_by_truncation"] += 1
                continue
            stats["summary_label_stripped"] += label != row["messages"][2]["content"]
            stats["summary_kept"] += 1
            split[name].append(new)

    if args.qa:
        for line in args.qa.open():
            messages = json.loads(line)["messages"]
            user = "\n".join(m["content"] for m in messages if m["role"] == "user")
            if loses_fact(user, messages[-1]["content"]):
                stats["qa_lost_fact"] += 1
                continue
            stats["qa_kept"] += 1
            split["val" if _is_val(user) else "train"].append({"messages": messages})

    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in split.items():
        with (args.out / f"{name}.jsonl").open("w") as out:
            out.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    stats["train"], stats["val"] = len(split["train"]), len(split["val"])
    print(json.dumps(dict(sorted(stats.items()))))


if __name__ == "__main__":
    main()
