"""G3c: labels for the public sandbox outputs (bench/matrix/results/g3c/data), in the exact training
format of the corpus (L5 facts block, production prompts), FR and EN.

    python3 g3c_label.py build --in public_g3c.retained.jsonl --out tasks.jsonl
    python3 g3c_label.py label --tasks tasks.jsonl --port P --tag 27b --out labels-27b.jsonl [--ids ids.txt] [--note]
    python3 g3c_label.py rows  --tasks tasks.jsonl --labels labels-27b.jsonl --out cand.jsonl
    JUDGE_PORT=P python3 j.py judge_corpus_2pass.py cand.jsonl g3c9 judge9/        # A7 9B, 2 passes
    python3 g3c_label.py flagged --cand cand.jsonl --verdicts judge9/verdicts-g3c9.jsonl --out flagged.jsonl
    JUDGE_PORT=P python3 j.py judge_corpus_2pass.py flagged.jsonl g3c27 judge27/   # same A7 prompt, 27B
    python3 g3c_label.py keep --cand cand.jsonl --v9 ... --v27 ... --out-train t.jsonl --out-val v.jsonl

- build: one task per distinct production user message; the teacher reads label.build_messages()
  (production system prompt, digest or compact output at 587 characters, L5 facts block);
- label: label.query() and label.judge() of the corpus (temperature 0, presence penalty 1, 64
  tokens, cleaning, 25 words at most); `--note` appends a language reminder to the teacher's
  system prompt only, as G3b did;
- rows: training row = TRAIN_SYSTEM of the language, production user message, label; a label that
  reads as the other language (lang_v3) is dropped;
- keep: a label stays if the A7 9B judge says ok on both passes, or if the 27B judge, reading the
  same A7 prompt, clears one the 9B flagged (X4a: 9B precision 53 %, 27B 85 %). Everything else
  goes. About 5 % of rows, by hash of the user message, go to validation.
Public data only: nothing here reads the personal corpus.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "results/finetune/loop/round-3/r3t2p3"))
import label  # noqa: E402
from lang_v3 import WORD, classify  # noqa: E402

from steph.digest import resolve  # noqa: E402

MAX_CHARS = 587
META = ("cmd", "exit", "family", "source", "fault", "scenario", "source_license")
NOTE = {
    "fr": "Réponds toujours en français, même si la sortie de la commande est en anglais.",
    "en": "Always answer in English, even when the command output is in French.",
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def read_jsonl(path) -> list[dict]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def build_tasks(recs: list[dict]) -> list[dict]:
    tasks, seen = [], set()
    for i, r in enumerate(recs):
        lang = r["lang"]
        msgs = label.build_messages(r, MAX_CHARS, lang)
        h = sha(msgs[1]["content"])
        if h in seen:
            continue
        seen.add(h)
        in_code = resolve(r["cmd"], r["exit"], r["output"], lang) is not None
        tasks.append({"id": f"{lang}:g3c:{i}", "lang": lang, **{k: r.get(k) for k in META},
                      "in_code": in_code, "teacher_messages": msgs})
    return tasks


def teacher_messages(msgs: list[dict], lang: str, note: bool) -> list[dict]:
    if not note:
        return msgs
    return [{**msgs[0], "content": msgs[0]["content"] + " " + NOTE[lang]}, *msgs[1:]]


def own_words(text: str, user: str) -> str:
    """Label words not copied from the input: copied tool words (make, test, error) say nothing
    about the language the teacher answered in."""
    copied = set(WORD.findall(user.lower().replace("'", " ").replace("’", " ")))
    return " ".join(w for w in WORD.findall(text.lower().replace("'", " ").replace("’", " ")) if w not in copied)


def candidate_row(task: dict, text: str | None) -> tuple[dict | None, str]:
    if not text:
        return None, "vide"
    got = classify(own_words(text, task["teacher_messages"][1]["content"]))
    if got is not None and got != task["lang"]:
        return None, "langue"
    messages = [{"role": "system", "content": label.train_system_for(task["lang"])},
                {"role": "user", "content": task["teacher_messages"][1]["content"]},
                {"role": "assistant", "content": text}]
    return {"id": task["id"], "lang": task["lang"], **{k: task.get(k) for k in META},
            "in_code": task.get("in_code"), "messages": messages}, "ok"


def final_verdict(v9: str, v27: str | None) -> str:
    if v9 == "ok":
        return "ok"
    return "ok" if v27 == "ok" else "rejet"


def is_val(user: str) -> bool:
    return int(sha(user), 16) % 20 == 0


def cmd_build(a) -> None:
    tasks = build_tasks(read_jsonl(a.inp))
    with open(a.out, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(t, ensure_ascii=False) + "\n" for t in tasks)
    print(json.dumps({"tasks": len(tasks), "fr": sum(t["lang"] == "fr" for t in tasks),
                      "in_code": sum(t["in_code"] for t in tasks)}))


def cmd_label(a) -> None:
    tasks = read_jsonl(a.tasks)
    if a.ids:
        want = {l.strip() for l in open(a.ids) if l.strip()}
        tasks = [t for t in tasks if t["id"] in want]
    out = Path(a.out)
    done = {r["id"] for r in read_jsonl(out)} if out.exists() else set()
    todo = [t for t in tasks if t["id"] not in done]
    print(f"{len(todo)} à étiqueter ({len(done)} déjà faites)", flush=True)
    lock = threading.Lock()

    def work(t: dict) -> dict:
        t0 = time.time()
        try:
            raw = label.query(a.port, teacher_messages(t["teacher_messages"], t["lang"], a.note), 64, a.timeout)
            text, reason = label.judge(raw)
        except Exception as e:  # noqa: BLE001
            raw, text, reason = "", None, f"erreur: {e!r}"
        return {"id": t["id"], "model": a.tag, "note": a.note, "raw": raw, "label": text, "reason": reason,
                "wall_s": round(time.time() - t0, 2)}

    with open(out, "a", encoding="utf-8") as f, concurrent.futures.ThreadPoolExecutor(a.parallel) as ex:
        for i, res in enumerate(ex.map(work, todo), 1):
            with lock:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
                f.flush()
            if i % 50 == 0:
                print(f"  {i}/{len(todo)}", flush=True)


def cmd_rows(a) -> None:
    labels = {r["id"]: r["label"] for r in read_jsonl(a.labels)}
    counts: dict = {}
    with open(a.out, "w", encoding="utf-8") as f:
        for t in read_jsonl(a.tasks):
            if t["id"] not in labels:
                continue
            row, why = candidate_row(t, labels[t["id"]])
            counts[why] = counts.get(why, 0) + 1
            if row:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(counts))


def verdicts_by_user(path) -> dict[str, str]:
    return {v["sha"]: v["verdict"] for v in read_jsonl(path)} if path and Path(path).exists() else {}


def cmd_flagged(a) -> None:
    v9 = verdicts_by_user(a.verdicts)
    n = 0
    with open(a.out, "w", encoding="utf-8") as f:
        for r in read_jsonl(a.cand):
            if v9.get(sha(r["messages"][1]["content"]), "erreur") != "ok":
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
    print(json.dumps({"flagged": n}))


def cmd_keep(a) -> None:
    v9, v27 = verdicts_by_user(a.v9), verdicts_by_user(a.v27)
    counts: dict = {"ok9": 0, "ok27": 0, "rejet": 0, "train": 0, "val": 0}
    with open(a.out_train, "w", encoding="utf-8") as ft, open(a.out_val, "w", encoding="utf-8") as fv:
        for r in read_jsonl(a.cand):
            h = sha(r["messages"][1]["content"])
            first = v9.get(h, "erreur")
            verdict = final_verdict(first, v27.get(h))
            counts["rejet" if verdict == "rejet" else "ok9" if first == "ok" else "ok27"] += 1
            if verdict == "rejet":
                continue
            val = is_val(r["messages"][1]["content"])
            counts["val" if val else "train"] += 1
            (fv if val else ft).write(json.dumps({**r, "source_set": "g3c_public"}, ensure_ascii=False) + "\n")
    print(json.dumps(counts))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build")
    s.add_argument("--in", dest="inp", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("label")
    s.add_argument("--tasks", required=True)
    s.add_argument("--port", type=int, required=True)
    s.add_argument("--tag", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--ids")
    s.add_argument("--note", action="store_true")
    s.add_argument("--parallel", type=int, default=1)
    s.add_argument("--timeout", type=float, default=900.0)
    s = sub.add_parser("rows")
    s.add_argument("--tasks", required=True)
    s.add_argument("--labels", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("flagged")
    s.add_argument("--cand", required=True)
    s.add_argument("--verdicts", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("keep")
    s.add_argument("--cand", required=True)
    s.add_argument("--v9", required=True)
    s.add_argument("--v27")
    s.add_argument("--out-train", required=True)
    s.add_argument("--out-val", required=True)
    a = ap.parse_args()
    {"build": cmd_build, "label": cmd_label, "rows": cmd_rows, "flagged": cmd_flagged, "keep": cmd_keep}[a.cmd](a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
