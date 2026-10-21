"""G3b language fix: English-prompt rows whose command output is in French, with an English label.

G3 SFT 42 answered in French under an English prompt when the command printed French (locale FR).
These rows teach the prompt language to win over the output language. Run on the corpus machine:

    python3 g3b_langfix.py select --raw corpus/macos.jsonl ... --n 500 --seed 42 --out subset.jsonl
    python3 g3b_langfix.py label --in subset.jsonl --port P --out labeled.jsonl   # teacher
    python3 g3b_langfix.py rows --labeled labeled.jsonl --out cand.jsonl
    JUDGE_PORT=P python3 j.py ../judge_corpus_2pass.py cand.jsonl langfix judge/   # untouched A7 judge
    python3 g3b_langfix.py keep --cand cand.jsonl --verdicts judge/verdicts-langfix.jsonl --n 300 --seed 42 --out langfix.jsonl

- select: raw records of the French corpus whose output reads as French (lang_v3 function words,
  at least MIN_FR_WORDS and more French than English), deduplicated on (cmd, output);
- label: label.py's corpus mode (production English prompt over the raw record, L5 facts block,
  output budget 587 like the mix summaries, same query and cleaning), but the teacher alone reads
  EN_NOTE after its system prompt: without it Qwen3.5 9B answered in French 116 times out of 281.
  The training row keeps the plain TRAIN_SYSTEM_EN;
- rows: the teacher's English label must read as English, otherwise the row is dropped;
- keep: only rows judged ok by both A7 passes (invention and douteux dropped, unlike the corpus).
Written files hold corpus text and stay on the machine; only counts are printed.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "results/finetune/loop/round-3/r3t2p3"))
from lang_v3 import EN, FR, WORD, classify  # noqa: E402

sys.path.insert(0, str(HERE.parent))
import label  # noqa: E402

MIN_FR_WORDS = 3
MAX_CHARS = 587
SOURCE = "langfix_en_fr"
EN_NOTE = "Always answer in English, even when the command output is in French."


def is_french_output(output: str) -> bool:
    words = WORD.findall(output.lower().replace("'", " ").replace("’", " "))
    fr = sum(w in FR for w in words)
    return fr >= MIN_FR_WORDS and fr > sum(w in EN for w in words)


def select(records: list[dict], n: int, seed: int) -> tuple[list[dict], dict]:
    french = [r for r in records if is_french_output(r["output"])]
    unique = list({(r["cmd"], r["output"]): r for r in french}.values())
    picked = random.Random(seed).sample(unique, min(n, len(unique)))
    return picked, {"records": len(records), "french": len(french), "unique": len(unique), "selected": len(picked)}


def teacher_messages(msgs: list[dict]) -> list[dict]:
    return [{**msgs[0], "content": msgs[0]["content"] + " " + EN_NOTE}, *msgs[1:]]


def labeled_row(rec: dict, msgs: list[dict], text: str) -> dict:
    train = [{"role": "system", "content": label.train_system_for("en")},
             {"role": "user", "content": msgs[1]["content"]}, {"role": "assistant", "content": text}]
    return {**rec, "input_messages": msgs, "label": text, "train_messages": train}


def label_all(records: list[dict], port: int, parallel: int) -> tuple[list[dict], dict]:
    counts: dict = {}
    lock = threading.Lock()

    def work(rec: dict) -> dict | None:
        msgs = label.build_messages(rec, MAX_CHARS, "en")
        try:
            text, reason = label.judge(label.query(port, teacher_messages(msgs), 64, 60.0))
        except Exception:
            text, reason = None, "erreur"
        with lock:
            counts[reason] = counts.get(reason, 0) + 1
        return labeled_row(rec, msgs, text) if text else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as ex:
        rows = [r for r in ex.map(work, records) if r]
    return rows, counts


def en_rows(labeled: list[dict]) -> tuple[list[dict], dict]:
    counts = {"labeled": len(labeled), "en": 0, "fr": 0, "undetermined": 0}
    rows = []
    for r in labeled:
        lang = classify(r["label"])
        counts[lang or "undetermined"] += 1
        if lang == "en":
            rows.append({"source": SOURCE, "messages": r["train_messages"]})
    return rows, counts


def keep_ok(rows: list[dict], verdicts: list[dict], n: int, seed: int) -> tuple[list[dict], dict]:
    by_sha = {v["sha"]: v["verdict"] for v in verdicts}
    counts = {"candidates": len(rows), "ok": 0, "invention": 0, "douteux": 0, "unjudged": 0}
    ok = []
    for r in rows:
        v = by_sha.get(hashlib.sha256(r["messages"][1]["content"].encode()).hexdigest())
        counts[v if v in ("ok", "invention", "douteux") else "unjudged"] += 1
        if v == "ok":
            ok.append(r)
    kept = random.Random(seed).sample(ok, min(n, len(ok)))
    return kept, {**counts, "kept": len(kept)}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--raw", type=Path, nargs="+", required=True)
    s.add_argument("--n", type=int, required=True)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--out", type=Path, required=True)
    lb = sub.add_parser("label")
    lb.add_argument("--in", dest="infile", type=Path, required=True)
    lb.add_argument("--port", type=int, required=True)
    lb.add_argument("--parallel", type=int, default=4)
    lb.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("rows")
    r.add_argument("--labeled", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    k = sub.add_parser("keep")
    k.add_argument("--cand", type=Path, required=True)
    k.add_argument("--verdicts", type=Path, required=True)
    k.add_argument("--n", type=int, required=True)
    k.add_argument("--seed", type=int, default=42)
    k.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "select":
        rows, counts = select([rec for p in a.raw for rec in read_jsonl(p)], a.n, a.seed)
    elif a.cmd == "label":
        rows, counts = label_all(read_jsonl(a.infile), a.port, a.parallel)
    elif a.cmd == "rows":
        rows, counts = en_rows(read_jsonl(a.labeled))
    else:
        rows, counts = keep_ok(read_jsonl(a.cand), read_jsonl(a.verdicts), a.n, a.seed)
    write_jsonl(a.out, rows)
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
