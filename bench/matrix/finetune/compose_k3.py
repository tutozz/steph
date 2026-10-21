"""Compose the unified K3 fine-tuning set in the format steph sends to the fine-tuned profile (B3).

    python3 compose_k3.py --fr-mix mix-judged --fr-raw corpus/*.jsonl snapshot-1/clean/*.jsonl \\
        --en final/macos.en.jsonl final/linux-low.en.jsonl --en-raw corpus/*.en.jsonl \\
        --en-exclude judge-rejects/en-reviewed.txt \\
        --feature detail=detail-k3.jsonl --feature start=final/start.jsonl ... \\
        --feature-exclude start=judge-rejects/h3a-start.txt ... --feature-raw corpus/features-*.jsonl \\
        --qa final/qa_train.jsonl --bench ../cases.json --speak-bench ../../../benchmark/data/v1 \\
        --max-chars 587 --out mix-k3

Sources and what happens to each row, in this order:
- fr_summary (P15 input, judge rejects and bench overlap already removed by compose_train.py),
  en_summary (K2), summary_residual (H3a errors and tests not resolved in code): matched back
  to the raw record, user turn rebuilt with today's digest() under --max-chars, system prompt
  TRAIN_SYSTEM or TRAIN_SYSTEM_EN, leading status word removed (steph says it in code, P9).
  English labels first go through fix_labels.py (invented « line N »), like K2.
- detail, start, progress, flux: kept as labeled, with their training prompt.
- qa (P15a), qa_en (R1, source ending in « .en »): kept as generated.
Every row: sha256 of the labeled user turn listed in the exclude file of its source (judge rejects) is
dropped, the same system and user turn seen twice is dropped,
anything sharing two long lines with a bench case or a Steph Speak Bench case (all languages,
dev and test) is dropped, then any label that loses a clause under steph.grounding.ground()
against its new input is dropped (P15). Split 95 / 5 by a hash of the user text.
Only counts are printed, never corpus text.

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
from fix_labels import fix_label, invented_number, output_of  # noqa: E402
from label import build_messages, strip_facts_block, train_system_for  # noqa: E402
from rebuild_p15 import loses_fact  # noqa: E402
from rebuild_p15 import strip_status as strip_status_fr  # noqa: E402

OUTPUT_MARKER = {"fr": "Sortie :\n", "en": "Output:\n"}
_LEADING_STATUS_EN = re.compile(r"^\s*(?:Success|Failed|Failure)(?:\s*[,(]?\s*(?:exit\s+)?code\s*\d+\)?)?\s*[.,:;!]?(?:\s+|$)")
MIN_LINE = 24
# the header of every summary turn is shared by thousands of rows: only output lines tell a case apart
_HEADER = re.compile(r"^(?:Commande|Statut|Durée|Command|Status|Duration)\s?:")
SUMMARY_SOURCES = {"fr_summary", "en_summary", "summary_residual"}


def strip_status(label: str, lang: str) -> str:
    if lang == "fr":
        return strip_status_fr(label)
    return _LEADING_STATUS_EN.sub("", label, count=1).strip()


def header_key(user: str, lang: str) -> str:
    return strip_facts_block(user, lang).split(OUTPUT_MARKER[lang], 1)[0]


def _output(user: str, lang: str) -> str:
    return user.split(OUTPUT_MARKER[lang], 1)[-1]


def match_raw(user: str, index: dict[str, list[dict]], lang: str) -> dict | None:
    """rebuild_p15.match_raw for any language: header first, then the digested output, then shared words."""
    candidates = index.get(header_key(user, lang), [])
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    old_output = _output(user, lang)
    for rec in candidates:
        if _output(build_messages(rec, 1500, lang)[1]["content"], lang) == old_output:
            return rec
    words = set(re.findall(r"\S{4,}", old_output))
    scored = sorted(((len(words & set(re.findall(r"\S{4,}", rec["output"]))), i) for i, rec in enumerate(candidates)),
                    reverse=True)
    best, runner_up = scored[0], scored[1]
    if best[0] > runner_up[0] or candidates[best[1]]["output"] == candidates[runner_up[1]]["output"]:
        return candidates[best[1]]
    return None


def rebuild_summary(label: str, rec: dict, max_chars: int, lang: str) -> list[dict]:
    return [{"role": "system", "content": train_system_for(lang)}, build_messages(rec, max_chars, lang)[1],
            {"role": "assistant", "content": strip_status(label, lang)}]


def long_lines(text: str) -> set[str]:
    return {line.strip() for line in text.splitlines() if len(line.strip()) >= MIN_LINE and not _HEADER.match(line)}


def contaminated(text: str, banned: set[str]) -> bool:
    return len(long_lines(text) & banned) >= 2


def bench_lines(paths: list[Path]) -> set[str]:
    lines: set[str] = set()
    for path in paths:
        for case in json.loads(path.read_text()):
            lines |= long_lines("\n".join(m["content"] for m in case["messages"] if m["role"] == "user"))
    return lines


def speak_bench_lines(data_dir: Path) -> set[str]:
    lines: set[str] = set()
    for path in sorted(Path(data_dir).glob("*/*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            outputs = [h["output"] for h in case["history"]] if case.get("task") == "qa" else [case.get("output", "")]
            for out in outputs:
                lines |= long_lines(out)
    return lines


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def read_jsonl(paths: list[Path]) -> list[dict]:
    return [json.loads(line) for path in paths for line in path.open(encoding="utf-8") if line.strip()]


def read_hashes(paths: list[Path]) -> set[str]:
    return {h for path in paths for h in path.read_text().split()}


def raw_index(paths: list[Path], lang: str) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for rec in read_jsonl(paths):
        index.setdefault(header_key(build_messages(rec, 1500, lang)[1]["content"], lang), []).append(rec)
    return index


def user_text(messages: list[dict]) -> str:
    return "\n".join(m["content"] for m in messages if m["role"] == "user")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fr-mix", type=Path, help="train.jsonl/val.jsonl de compose_train.py (entrée de P15)")
    ap.add_argument("--fr-raw", type=Path, nargs="*", default=[])
    ap.add_argument("--en", type=Path, nargs="*", default=[])
    ap.add_argument("--en-raw", type=Path, nargs="*", default=[])
    ap.add_argument("--en-exclude", type=Path, nargs="*", default=[])
    ap.add_argument("--feature", action="append", default=[],
                    help="nom=fichier ; summary_residual est reconstruit ; nom en « _en » : anglais")
    ap.add_argument("--feature-exclude", action="append", default=[], help="nom=fichier d'empreintes, par fonctionnalité")
    ap.add_argument("--feature-raw", type=Path, nargs="*", default=[])
    ap.add_argument("--qa", type=Path, nargs="*", default=[], help="questions ; source « .en » : anglais (qa_en)")
    ap.add_argument("--bench", type=Path, nargs="*", default=[])
    ap.add_argument("--speak-bench", type=Path)
    ap.add_argument("--max-chars", dest="max_chars", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    banned_bench = bench_lines(args.bench)
    banned_speak = speak_bench_lines(args.speak_bench) if args.speak_bench else set()
    # a judge reject is about one label: the detail and the summary of one output share the user turn
    excluded: dict[str, set[str]] = collections.defaultdict(set)
    excluded["en_summary"] = read_hashes(args.en_exclude)
    for spec in args.feature_exclude:
        name, path = spec.split("=", 1)
        excluded[name] |= read_hashes([Path(path)])

    # (source, lang, messages as labeled, raw index or None)
    todo: list[tuple[str, str, list[dict], dict | None]] = []
    if args.fr_mix:
        fr_index = raw_index(args.fr_raw, "fr")
        for name in ("train", "val"):
            todo += [("fr_summary", "fr", r["messages"], fr_index) for r in read_jsonl([args.fr_mix / f"{name}.jsonl"])]
    if args.en:
        en_index = raw_index(args.en_raw, "en")
        todo += [("en_summary", "en", r["messages"], en_index) for r in read_jsonl(args.en)]
    feature_index = raw_index(args.feature_raw, "fr") if args.feature_raw else {}
    for spec in args.feature:
        name, path = spec.split("=", 1)
        index = feature_index if name == "summary_residual" else None
        lang = "en" if name.endswith("_en") else "fr"
        todo += [(name, lang, r["messages"], index) for r in read_jsonl([Path(path)])]
    for r in read_jsonl(args.qa):
        english = r.get("source", "").endswith(".en")
        todo.append(("qa_en" if english else "qa", "en" if english else "fr", r["messages"], None))

    stats: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    seen: set[str] = set()
    split = {"train": [], "val": []}
    kept_by_lang: collections.Counter = collections.Counter()
    for source, lang, messages, index in todo:
        st = stats[source]
        user = user_text(messages[:-1])
        key = messages[0]["content"] + "\x00" + user
        if key in seen:
            st["duplicate"] += 1
            continue
        seen.add(key)
        if sha(messages[1]["content"]) in excluded[source]:
            st["judge_reject"] += 1
            continue
        if contaminated(user, banned_bench):
            st["bench"] += 1
            continue
        if contaminated(user, banned_speak):
            st["speak_bench"] += 1
            continue
        label = messages[-1]["content"]
        if source == "en_summary":
            output = output_of(messages[1]["content"], "en")
            label = fix_label(label, output, "en")
            if not label or invented_number(label, output):
                st["invented_line_or_number"] += 1
                continue
        if source in SUMMARY_SOURCES:
            rec = match_raw(messages[1]["content"], index, lang)
            if rec is None:
                st["unmatched"] += 1
                continue
            messages = rebuild_summary(label, rec, args.max_chars, lang)
            if not messages[-1]["content"]:
                st["status_only"] += 1
                continue
        new_user = user_text(messages[:-1])
        if loses_fact(new_user, messages[-1]["content"]):
            st["lost_fact"] += 1
            continue
        st["kept"] += 1
        kept_by_lang[lang] += 1
        name = "val" if int(sha(new_user), 16) % 20 == 0 else "train"
        split[name].append({"source": source, "messages": messages})

    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in split.items():
        with (args.out / f"{name}.jsonl").open("w", encoding="utf-8") as out:
            out.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    report = {source: dict(sorted(c.items())) for source, c in sorted(stats.items())}
    report["kept_by_lang"] = dict(kept_by_lang)
    report["train"], report["val"] = len(split["train"]), len(split["val"])
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
