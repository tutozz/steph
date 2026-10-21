"""G3: DPO pairs for the fine-tuned Gemma 4 E2B, built on the corpus machine.

    python3 g3_pairs.py select --final DIR --final-extra DIR --prints prints.json --total 900 --out selected.jsonl
    python3 ../loop/r3t4/onpolicy_sample.py sample --selected selected.jsonl --ports ... --n 4 --out samples.jsonl
    JUDGE_PORT=... python3 j.py ../loop/r3t4/mask_pairs.py judge --pass A|B ...   # untouched A7 judge, cache
    python3 g3_pairs.py build --selected selected.jsonl --samples samples.jsonl --cache cache/ --out pairs/

- select: R3-T4 selection (same files, reaches_model, bench fingerprints), but the user turn is the one
  the generic production profile sends to Gemma (SUMMARY_SYSTEM, digest at cfg.summary_chars).
- build: chosen = the 27B label; rejected = an on-policy output judged invented by both A7 passes
  (at most max_pairs distinct per entry), or, for a question whose answer is in the history, an
  abstention. Every present-answer question gets an abstention pair (R2 trap: DPO without them
  taught "Pas dans l'historique." when the answer was there).
Written files hold corpus text and stay on the machine; only counts are printed.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "loop" / "r3t4"))

from mask_pairs import cache_key, final_verdict, load_cache, load_rows  # noqa: E402
from qa_corpus import CANONICAL_ABSENT_BY_LANG, is_abstention  # noqa: E402


def entry_pairs(entry: dict, outs: list[dict], verdicts: dict[str, dict], max_pairs: int = 2) -> list[dict]:
    label = entry["label"].strip()
    present = entry["task"] == "qa" and not is_abstention(label)
    rejected: list[tuple[str, str]] = []
    for s in outs:
        text = s["text"].strip()
        if not text or text == label or text in (r for r, _ in rejected):
            continue
        if present and is_abstention(text):
            rejected.append((text, "abstention"))
            continue
        v = verdicts.get(cache_key(entry["id"], s["text"]))
        if v and v["final"] == "invention":
            rejected.append((text, "invention"))
    rejected = rejected[:max_pairs]
    if present and not any(k == "abstention" for _, k in rejected):
        rejected.append((CANONICAL_ABSENT_BY_LANG[entry["lang"]], "abstention"))
    return [{"id": entry["id"], "task": entry["task"], "lang": entry["lang"], "prompt": entry["messages"],
             "chosen": label, "rejected": r, "kind": k} for r, k in rejected]


def split_val(pairs: list[dict], frac: float) -> tuple[list[dict], list[dict]]:
    is_val = lambda p: int(hashlib.sha256(p["id"].encode()).hexdigest()[:8], 16) / 16**8 < frac  # noqa: E731
    return [p for p in pairs if not is_val(p)], [p for p in pairs if is_val(p)]


def verdict_table(cache: Path) -> dict[str, dict]:
    va, vb = load_cache(cache, "A"), load_cache(cache, "B")
    out = {}
    for k, a in va.items():
        b = vb.get(k)
        final = ("ok" if a["verdict"] == "ok" else "douteux") if b is None else final_verdict(a["verdict"], b["verdict"])
        out[k] = {"final": final, "inventions": a["inventions"] + (b["inventions"] if b else [])}
    return out


def build(args) -> None:
    entries, outs = load_rows(args.selected, args.samples)
    verdicts = verdict_table(args.cache)
    pairs = [p for eid, e in entries.items() for p in entry_pairs(e, outs.get(eid, []), verdicts, args.max_pairs)]
    train, val = split_val(pairs, args.val_frac)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("pairs-train.jsonl", train), ("pairs-val.jsonl", val)):
        with (args.out / name).open("w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    finals = collections.Counter(verdicts.get(cache_key(eid, s["text"]), {"final": "non_juge"})["final"]
                                 for eid, v in outs.items() for s in v if s["text"].strip())
    report = {"entries": len(entries), "entries_sampled": len(outs), "outputs_by_final": dict(finals),
              "pairs": len(pairs), "train": len(train), "val": len(val),
              "by_kind": dict(collections.Counter(f"{p['task']}/{p['kind']}" for p in pairs)),
              "by_lang": dict(collections.Counter(p["lang"] for p in pairs))}
    (args.out / "pairs-counts.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False))


def generic_messages(rec: dict, lang: str) -> list[dict]:
    """Generic production profile over a parsed corpus row; the L5 facts block comes from the row
    (data/final-x4-l5), since it cannot be recomputed from an already digested output."""
    import onpolicy_sample as op
    from steph import prompts
    from steph.config import Config

    chars = Config().summary_chars
    out = op.digest(rec["cmd"], rec["output"], chars, lang) or op.compact_output(rec["output"].splitlines(), chars)
    return prompts.summary_messages(rec["cmd"], rec["exit"], rec["duration"], out, rec["nlines"], language=lang,
                                    facts=rec.get("facts"))


def select_generic(argv: list[str]) -> None:
    import onpolicy_sample as op

    op.production_messages = generic_messages
    sys.argv = ["onpolicy_sample.py", "select", *argv]
    op.main()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "select":
        select_generic(sys.argv[2:])
        return
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.add_argument("--selected", type=Path, required=True)
    p.add_argument("--samples", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-pairs", type=int, default=2)
    p.add_argument("--val-frac", type=float, default=0.08)
    build(ap.parse_args())


if __name__ == "__main__":
    main()
