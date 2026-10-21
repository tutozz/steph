"""G5 data helpers, run on the corpus machine (written files hold corpus text and stay there).

    python3 g5_data.py qa-present --data <mix> --out <dir>
    python3 g5_data.py pairs --data <qa-present dir> --gen gen.jsonl --verdicts verdicts.jsonl --out <dir>
    python3 g5_data.py generic --data <mix> --out <dir>
    python3 g5_data.py distill --data <mix> --gen gen.jsonl --verdicts verdicts.jsonl --out <dir>

- qa-present: the question rows of a mix whose label is an answer, not an abstention. R2 showed that
  the R1 DPO makes the 350M say "Pas dans l'historique" when the answer is there (-18.3 pts on test);
- pairs: DPO pairs on those rows only. chosen = the label; rejected = an SFT output that abstains, or
  that both A7 passes call an invention (at most max_per_prompt distinct outputs per prompt);
- generic: the mix with the production generic system prompts (gemma_format.to_generic), the input
  the G3b Gemma teacher was trained on;
- distill: sequence-level distillation from G3b. A train row takes the teacher's output instead of its
  label only when both A7 passes say ok, the output is in the row's language (lang_v3), and, for a
  question, it abstains exactly when the label abstains. Val rows keep their labels, so the val loss
  stays comparable between variants.
Only counts are printed.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "results/finetune/loop/round-3/r3t2p3"))
from lang_v3 import classify  # noqa: E402
from qa_corpus import is_abstention  # noqa: E402

QA_SOURCES = {"qa", "qa_en"}


def key(context: str, phrase: str) -> str:
    """Same key as pref/judge_outputs.py: verdicts.jsonl is looked up with it."""
    return hashlib.sha256((context + "\x00" + phrase).encode()).hexdigest()


def row_lang(source: str) -> str:
    return "en" if source.endswith("_en") or source.startswith("en_") or source == "langfix_en_fr" else "fr"


def qa_present(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("source") in QA_SOURCES and not is_abstention(r["messages"][-1]["content"])]


def qa_present_pairs(rows: list[dict], gens: list[dict], verdicts: dict[str, str],
                     max_per_prompt: int) -> tuple[list[dict], dict]:
    counts = {"absent_rows": 0, "present_rows": 0, "abstention": 0, "invention": 0}
    present = {}
    for i, r in enumerate(rows):
        if r.get("source") not in QA_SOURCES:
            continue
        if is_abstention(r["messages"][-1]["content"]):
            counts["absent_rows"] += 1
        else:
            present[i] = r
            counts["present_rows"] += 1
    rejected: dict[int, list[str]] = {}
    for g in gens:
        r = present.get(g["idx"])
        if r is None:
            continue
        out = g["out"]
        if is_abstention(out):
            why = "abstention"
        elif verdicts.get(key(r["messages"][1]["content"], out)) == "invention":
            why = "invention"
        else:
            continue
        bucket = rejected.setdefault(g["idx"], [])
        if out in bucket or len(bucket) >= max_per_prompt:
            continue
        bucket.append(out)
        counts[why] += 1
    pairs = [{"prompt": present[i]["messages"][:-1], "chosen": present[i]["messages"][-1]["content"], "rejected": out}
             for i in sorted(rejected) for out in rejected[i]]
    return pairs, {**counts, "pairs": len(pairs), "prompts": len(rejected)}


def distill_rows(rows: list[dict], teacher: dict[int, str], verdicts: dict[str, str]) -> tuple[list[dict], dict]:
    counts = {"rows": len(rows), "replaced": 0, "no_output": 0, "invention": 0, "douteux": 0, "unjudged": 0,
              "language": 0, "abstention_mismatch": 0}
    out_rows = []
    for i, r in enumerate(rows):
        out = teacher.get(i)
        label = r["messages"][-1]["content"]
        why = None
        if not out:
            why = "no_output"
        else:
            v = verdicts.get(key(r["messages"][1]["content"], out))
            got = classify(out)
            if v != "ok":
                why = v if v in ("invention", "douteux") else "unjudged"
            elif got is not None and got != row_lang(r.get("source", "")):
                why = "language"
            elif r.get("source") in QA_SOURCES and is_abstention(out) != is_abstention(label):
                why = "abstention_mismatch"
        if why:
            counts[why] += 1
            out_rows.append(r)
            continue
        counts["replaced"] += 1
        out_rows.append({**r, "messages": r["messages"][:-1] + [{"role": "assistant", "content": out}]})
    return out_rows, counts


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def read_verdicts(path: Path) -> dict[str, str]:
    return {v["key"]: v["final"] for v in read_jsonl(path)}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["qa-present", "pairs", "generic", "distill"])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gen", type=Path)
    ap.add_argument("--verdicts", type=Path)
    ap.add_argument("--max-per-prompt", type=int, default=3)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    split_rows = {s: read_jsonl(a.data / f"{s}.jsonl") for s in ("train", "val")}
    counts: dict = {}
    if a.cmd == "qa-present":
        for s, rows in split_rows.items():
            kept = qa_present(rows)
            write_jsonl(a.out / f"{s}.jsonl", kept)
            counts[s] = len(kept)
    elif a.cmd == "generic":
        from gemma.gemma_format import to_generic
        for s, rows in split_rows.items():
            conv = [(r, *to_generic(r["messages"])) for r in rows]
            write_jsonl(a.out / f"{s}.jsonl", [{**r, "messages": m} for r, m, _ in conv])
            counts[s] = {"rows": len(rows), "unknown_system": sum(not k for _, _, k in conv)}
    else:
        gens = read_jsonl(a.gen)
        verdicts = read_verdicts(a.verdicts)
        for s, rows in split_rows.items():
            g = [x for x in gens if x["split"] == s]
            if a.cmd == "pairs":
                pairs, counts[s] = qa_present_pairs(rows, g, verdicts, a.max_per_prompt)
                write_jsonl(a.out / f"pairs-{s}.jsonl", pairs)
            elif s == "train":
                teacher = {x["idx"]: x["out"] for x in sorted(g, key=lambda x: x["seed"])}
                out_rows, counts[s] = distill_rows(rows, teacher, verdicts)
                write_jsonl(a.out / "train.jsonl", out_rows)
            else:
                write_jsonl(a.out / "val.jsonl", rows)
                counts[s] = {"rows": len(rows), "kept_labels": len(rows)}
        if a.cmd == "pairs":
            json.dump(counts, open(a.out / "pairs-counts.json", "w"), indent=1)
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
