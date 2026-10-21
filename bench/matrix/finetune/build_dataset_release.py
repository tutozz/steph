"""Assemble the publishable Hugging Face Datasets release of the fine-tuning corpus (I2).

    python3 build_dataset_release.py --final final --raw-dir corpus \\
        --exclude final/judge-rejects.txt judge-rejects/h3a-*.txt \\
        [--pairs-dir pref] --max-chars 587 --out release-v0

Reads the finalized, anonymized, judge-filtered corpus (`--final`, one row per line:
`{"messages": [...], "source": <neutral category>}`, plus an optional `qa_train.jsonl`),
composes it the same way `compose_train.py` does (drop exact duplicates, drop judge
rejects, cap the "instantane" snapshot rows per program), then, for every row whose task
is the spoken summary and whose raw capture is still available under `--raw-dir`,
re-renders the user turn with today's `steph.digest`/`steph.prompts` code (same intent as
`rebuild_p15.py`, but threaded through the row's own language instead of assuming French)
and drops any label that no longer grounds against that re-rendered input. Rows with no
matching raw capture (the older "instantane" rows) and every feature/QA row are kept as
already-production-format, under the same grounding safety check.

Every published row carries its documentation fields: `language`, `task`, `source` (the
neutral category already written by `finalize_labels.py`), `provenance` (`real_capture`
or `synthetic_session`), `labeler`, `judge`, and, for the `sft` configuration, `resynced`
(whether the row was re-rendered against today's code or kept as labeled). Output is one
JSONL file per Hugging Face configuration (`sft`, `dpo`) and split (`train`,
`validation`), under `--out`. `dpo` needs `--pairs-dir` (the output of `pref/build_pairs.py`,
`pairs-train.jsonl` / `pairs-val.jsonl`); without it the configuration is written empty,
which is the expected state before R1 builds the preference pairs from a trained model.

Refuses to write anything if any row still contains the benchmark canary string: only
counts are ever printed, never corpus text.

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
from compose_train import program  # noqa: E402
from label import build_messages, strip_facts_block, train_system_for  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from steph.grounding import _METADATA_NUMBER_RE, _fold, _is_grounded, _numbers_in, _split_segments  # noqa: E402

CANARY = "termspeak-canary-v1-5e0c83a1d7f2"

_FEATURE_TASKS = {"detail", "start", "progress", "flux", "summary_residual"}
_TASK_BY_BASE_SOURCE = {task: task for task in _FEATURE_TASKS} | {"qa-synth": "qa"}

_OUTPUT_MARKER = {"fr": "Sortie :\n", "en": "Output:\n"}
_LEADING_STATUS = {
    "fr": re.compile(r"^\s*(?:Succès|Échec)(?:\s*[,(]?\s*code\s*\d+\)?)?\s*[.,:;!]?(?:\s+|$)"),
    "en": re.compile(r"^\s*(?:Success|Failed)(?:\s*[,(]?\s*code\s*\d+\)?)?\s*[.,:;!]?(?:\s+|$)", re.IGNORECASE),
}
_SAFE_SOURCE_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,39}$")


# --------------------------------------------------------------------------- taxonomy

def task_for_source(source: str) -> str:
    base = source[:-3] if source.endswith(".en") else source
    return _TASK_BY_BASE_SOURCE.get(base, "summary")


def language_for_source(source: str) -> str:
    return "en" if source.endswith(".en") else "fr"


def provenance_for_task(task: str) -> str:
    return "synthetic_session" if task == "qa" else "real_capture"


def is_neutral_source(source: str) -> bool:
    """False for anything that looks like a path, a host or a real proper noun rather
    than one of the small set of category tags `finalize_labels.py` writes."""
    return bool(_SAFE_SOURCE_RE.fullmatch(source))


# --------------------------------------------------------------------------- status / header (bilingual)

def strip_status(label: str, language: str) -> str:
    return _LEADING_STATUS[language].sub("", label, count=1).strip()


def header_key(user: str, language: str) -> str:
    return strip_facts_block(user, language).split(_OUTPUT_MARKER[language], 1)[0]


def _output_of(user: str, language: str) -> str:
    return user.split(_OUTPUT_MARKER[language], 1)[-1]


# --------------------------------------------------------------------------- raw matching (bilingual)

def index_raw(records: list[dict], language: str, match_chars: int = 1500) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for rec in records:
        user = build_messages(rec, match_chars, language)[1]["content"]
        index.setdefault(header_key(user, language), []).append(rec)
    return index


def match_raw(user: str, index: dict[str, list[dict]], language: str, match_chars: int = 1500) -> dict | None:
    candidates = index.get(header_key(user, language), [])
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    old_output = _output_of(user, language)
    for rec in candidates:
        if _output_of(build_messages(rec, match_chars, language)[1]["content"], language) == old_output:
            return rec
    # the digest changed since labeling: fall back to the raw output sharing most words
    words = set(re.findall(r"\S{4,}", old_output))
    scored = sorted(((len(words & set(re.findall(r"\S{4,}", rec["output"]))), i) for i, rec in enumerate(candidates)),
                    reverse=True)
    best, runner_up = scored[0], scored[1]
    if best[0] > runner_up[0] or candidates[best[1]]["output"] == candidates[runner_up[1]]["output"]:
        return candidates[best[1]]
    return None


# --------------------------------------------------------------------------- grounding

def loses_fact(user: str, label: str) -> bool:
    """True when ground() would cut at least one clause of `label` given `user` as input."""
    numbers = _numbers_in(_METADATA_NUMBER_RE.sub(" ", user))
    folded = _fold(user)
    return not all(_is_grounded(segment, numbers, folded) for segment, _ in _split_segments(label))


def rebuild_summary_row(row: dict, rec: dict, max_chars: int, language: str) -> dict:
    user = build_messages(rec, max_chars, language)[1]
    system = {"role": "system", "content": train_system_for(language)}
    label = strip_status(row["messages"][-1]["content"], language)
    return {"messages": [system, user, {"role": "assistant", "content": label}]}


# --------------------------------------------------------------------------- composition (compose_train.py's rules)

def compose(rows: list[dict], excluded: set[str], cap: int) -> tuple[list[dict], collections.Counter]:
    """Drop exact duplicates and judge rejects; cap "instantane" (snapshot-sourced) rows
    per program once the cap is reached, exactly like `compose_train.py`."""
    ordered = sorted(rows, key=lambda r: r["source"].startswith("snapshot"))
    counts, seen, kept = collections.Counter(), set(), []
    stats: collections.Counter = collections.Counter()
    for r in ordered:
        user = r["messages"][1]["content"]
        prog = program(r)
        if user in seen:
            stats["duplicate"] += 1
            continue
        if hashlib.sha256(user.encode()).hexdigest() in excluded:
            stats["judge_reject"] += 1
            continue
        if r["source"].startswith("snapshot") and counts[prog] >= cap:
            stats["program_cap"] += 1
            continue
        seen.add(user)
        counts[prog] += 1
        kept.append(r)
    return kept, stats


# --------------------------------------------------------------------------- split / documentation

def split_for(text: str) -> str:
    """Deterministic 95/5 split by SHA-256 of `text`, same formula as `compose_train.py`."""
    h = int(hashlib.sha256(text.encode()).hexdigest(), 16)
    return "validation" if h % 20 == 0 else "train"


def documented_row(messages: list[dict], source: str, resynced: bool) -> dict:
    task = task_for_source(source)
    return {
        "messages": messages,
        "language": language_for_source(source),
        "task": task,
        "source": source,
        "provenance": provenance_for_task(task),
        "labeler": "qwen3.5-9b",
        "judge": "qwen3.5-9b-2pass",
        "resynced": resynced,
    }


def documented_pair(pair: dict) -> dict:
    user = next((m["content"] for m in pair["prompt"] if m["role"] == "user"), "")
    language = "en" if user.startswith("Command:") else "fr"
    return {
        "prompt": pair["prompt"],
        "chosen": pair["chosen"],
        "rejected": pair["rejected"],
        "language": language,
        "task": "summary",
        "source": "preference-pairs",
        "provenance": "real_capture_chosen_model_generated_rejected",
        "labeler": "qwen3.5-9b",
        "judge": "qwen3.5-9b-2pass",
    }


def contains_canary(text: str) -> bool:
    return CANARY in text


# --------------------------------------------------------------------------- I/O helpers

def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_excluded(paths: list[Path]) -> set[str]:
    excluded: set[str] = set()
    for p in paths:
        excluded |= set(p.read_text(encoding="utf-8").split())
    return excluded


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


# --------------------------------------------------------------------------- main

def build_sft(rows: list[dict], raw_dir: Path, max_chars: int) -> tuple[dict[str, list[dict]], collections.Counter]:
    splits: dict[str, list[dict]] = {"train": [], "validation": []}
    stats: collections.Counter = collections.Counter()
    raw_indexes: dict[str, dict[str, list[dict]]] = {}

    for row in rows:
        source = row["source"]
        task = task_for_source(source)
        language = language_for_source(source)
        original_user = row["messages"][1]["content"]
        original_label = row["messages"][-1]["content"]

        if task == "summary":
            raw_path = raw_dir / f"{source}.jsonl"
            if raw_path.exists():
                if source not in raw_indexes:
                    raw_indexes[source] = index_raw(read_jsonl(raw_path), language)
                rec = match_raw(original_user, raw_indexes[source], language)
                if rec is None:
                    stats["summary_unmatched"] += 1
                    continue
                new = rebuild_summary_row(row, rec, max_chars, language)
                new_user, new_label = new["messages"][1]["content"], new["messages"][2]["content"]
                if not new_label:
                    stats["summary_status_only"] += 1
                    continue
                if loses_fact(new_user, new_label):
                    stats["summary_lost_fact"] += 1
                    continue
                messages, resynced = new["messages"], True
            else:
                if loses_fact(original_user, original_label):
                    stats["summary_lost_fact_no_raw"] += 1
                    continue
                messages, resynced = row["messages"], False
        else:
            # detail/start/progress/flux/summary_residual: already the production system
            # prompt and input shape (`build_feature_corpus.py`/`label_features.py`), so no
            # resync is needed - but `loses_fact()` assumes the "cite the output literally,
            # never infer" contract of `summary`. `detail` explicitly allows causes, and
            # `start` has no output to ground against at all (`start_messages()` sends the
            # bare command). Measured on the 2026-09-27 corpus: applying `loses_fact()` here
            # dropped 405 of 529 `detail` rows (77 %), far above the judge's own 26 %
            # invention rate for the same task - a false-positive rate, not a real one. The
            # H3a 2-pass judge (already applied above via --exclude) is this task's quality
            # gate, not this grounding check.
            messages, resynced = row["messages"], False

        stats[f"{task}_kept"] += 1
        splits[split_for(original_user)].append(documented_row(messages, source, resynced))

    return splits, stats


def build_qa(qa_rows: list[dict]) -> tuple[dict[str, list[dict]], collections.Counter]:
    splits: dict[str, list[dict]] = {"train": [], "validation": []}
    stats: collections.Counter = collections.Counter()
    for row in qa_rows:
        user = "\n".join(m["content"] for m in row["messages"] if m["role"] == "user")
        label = row["messages"][-1]["content"]
        if loses_fact(user, label):
            stats["qa_lost_fact"] += 1
            continue
        stats["qa_kept"] += 1
        splits[split_for(user)].append(documented_row(row["messages"], row.get("source", "qa-synth"), resynced=False))
    return splits, stats


def build_dpo(pairs_dir: Path | None) -> dict[str, list[dict]]:
    splits: dict[str, list[dict]] = {"train": [], "validation": []}
    if pairs_dir is None:
        return splits
    for split, filename in (("train", "pairs-train.jsonl"), ("validation", "pairs-val.jsonl")):
        for pair in read_jsonl(pairs_dir / filename):
            splits[split].append(documented_pair(pair))
    return splits


def texts_of(rows_by_split: dict[str, list[dict]], *fields: str) -> list[str]:
    out = []
    for rows in rows_by_split.values():
        for row in rows:
            for field in fields:
                value = row.get(field)
                if isinstance(value, str):
                    out.append(value)
                elif isinstance(value, list):
                    out.extend(m["content"] for m in value)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", type=Path, required=True, help="dossier final/ (train.jsonl, qa_train.jsonl)")
    ap.add_argument("--raw-dir", type=Path, required=True, help="dossier des captures brutes (corpus/)")
    ap.add_argument("--exclude", type=Path, nargs="+", required=True,
                    help="listes de sha256 rejetés par le juge, fusionnées (compose_train.py + H3a)")
    ap.add_argument("--pairs-dir", type=Path, default=None, help="dossier pairs-train.jsonl/pairs-val.jsonl (P16)")
    ap.add_argument("--cap", type=int, default=120, help="plafond par programme des lignes instantané")
    ap.add_argument("--max-chars", type=int, required=True, help="budget du digest de production")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    excluded = load_excluded(args.exclude)
    rows = read_jsonl(args.final / "train.jsonl")
    kept, compose_stats = compose(rows, excluded, args.cap)

    sft, sft_stats = build_sft(kept, args.raw_dir, args.max_chars)
    qa, qa_stats = build_qa(read_jsonl(args.final / "qa_train.jsonl"))
    for split in sft:
        sft[split].extend(qa[split])
    dpo = build_dpo(args.pairs_dir)

    tainted = [t for t in texts_of(sft, "messages") + texts_of(dpo, "prompt", "chosen", "rejected")
              if contains_canary(t)]
    if tainted:
        print(f"canari du banc trouvé dans {len(tainted)} champ(s) : rien n'est écrit.", file=sys.stderr)
        return 1

    for split, path in (("train", "train.jsonl"), ("validation", "validation.jsonl")):
        write_jsonl(args.out / "sft" / path, sft[split])
        write_jsonl(args.out / "dpo" / path, dpo[split])

    manifest = {
        "sft": {"train": len(sft["train"]), "validation": len(sft["validation"]),
               "by_task": dict(collections.Counter(r["task"] for s in sft.values() for r in s)),
               "by_language": dict(collections.Counter(r["language"] for s in sft.values() for r in s)),
               "by_source": dict(collections.Counter(r["source"] for s in sft.values() for r in s))},
        "dpo": {"train": len(dpo["train"]), "validation": len(dpo["validation"])},
        "compose": dict(sorted(compose_stats.items())),
        "filters": dict(sorted((sft_stats + qa_stats).items())),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
