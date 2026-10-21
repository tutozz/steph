"""X4 : réétiquetage décidé en X4a, sur la machine qui porte le corpus (xeon, data/final/).

Qwen3.5 27B pour les résumés FR et EN, la progression et le flux ; Qwen3.5 9B pour le détail K3,
régénéré avec la jointure en points de `clean(points=True)` ; les rejets du juge K3 sur le détail
sont rejugés au 27B (2 passes, rejet sur « invention »). Même requête que label.query(), mêmes
prompts d'enseignant que X4a.

    python3 x4_relabel.py build    --final DIR --hashes DIR --out tasks.jsonl
    python3 x4_relabel.py label    --tasks tasks.jsonl --task fr_summary --port 8950 --model-tag 27b --out labels.jsonl
    python3 x4_relabel.py judge    --tasks tasks.jsonl --labels labels-detail.jsonl --port 8950 --out judge.jsonl
    python3 x4_relabel.py assemble --final DIR --tasks tasks.jsonl --labels labels-*.jsonl --judge judge.jsonl --out DIR

Les fichiers écrits contiennent du texte de corpus et restent sur la machine ; `assemble` n'imprime
que des comptes.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import judge_lib  # noqa: E402
from label import judge as clean_summary  # noqa: E402
from label_features import TEACHER_DETAILS_SYSTEM, TRAIN_DETAILS_SYSTEM, judge as clean_feature  # noqa: E402
from x4a_audit import query_full  # noqa: E402

from steph.prompts import PROGRESS_SYSTEM, SUMMARY_SYSTEM, SUMMARY_SYSTEM_EN  # noqa: E402

# tâche : (fichiers de final/, prompt de l'enseignant, max_tokens)
TASKS = {
    "fr_summary": (["macos", "linux-low", "linux-dev", "snapshot-linux-dev", "snapshot-linux-low"], SUMMARY_SYSTEM, 64),
    "en_summary": (["macos.en", "linux-low.en"], SUMMARY_SYSTEM_EN, 64),
    "progress": (["progress", "flux"], PROGRESS_SYSTEM, 120),
    "detail": (["detail"], TEACHER_DETAILS_SYSTEM, 120),
}
FEATURE_WORDS = {"detail": 60, "progress": 12}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def build_tasks(final: Path, hashes: Path) -> list[dict]:
    k3_all = set((hashes / "detail-k3-all.txt").read_text().split())
    k3_rejected = set((hashes / "detail-k3.txt").read_text().split())
    tasks: list[dict] = []
    for task, (files, system, max_tokens) in TASKS.items():
        seen: set[str] = set()
        for f in files:
            for row in read_jsonl(final / f"{f}.jsonl"):
                user = row["messages"][1]["content"]
                h = sha(user)
                if h in seen or (task == "detail" and h not in k3_all):
                    continue
                seen.add(h)
                tasks.append({"tid": f"{task}:{h[:16]}", "task": task, "sha": h, "max_tokens": max_tokens,
                              "k3_rejected": task == "detail" and h in k3_rejected,
                              "teacher_messages": [{"role": "system", "content": system},
                                                   {"role": "user", "content": user}]})
    return tasks


def clean_for(task: str, raw: str) -> tuple[str | None, str]:
    if task.endswith("summary"):
        return clean_summary(raw)
    return clean_feature(raw, FEATURE_WORDS[task], task)


def assemble(final: Path, tasks: list[dict], labels: dict[str, str | None], verdicts: dict[str, str],
             out: Path) -> dict:
    """Réécrit les fichiers de final/ touchés par une tâche. Une ligne sort si sa nouvelle étiquette est
    rejetée (clean ou juge), ou si c'est un rejet K3 du détail que le 27B n'a pas blanchi."""
    by_key = {(t["task"], t["sha"]): t for t in tasks}
    out.mkdir(parents=True, exist_ok=True)
    counts: dict = {}
    for task, (files, _, _) in TASKS.items():
        c = counts.setdefault(task, {"rows": 0, "changed": 0, "identical": 0, "dropped": 0})
        for f in files:
            kept = []
            for row in read_jsonl(final / f"{f}.jsonl"):
                t = by_key.get((task, sha(row["messages"][1]["content"])))
                if t is None:
                    continue  # détail hors K3
                c["rows"] += 1
                new = labels.get(t["tid"])
                if t["k3_rejected"] and verdicts.get(t["tid"]) not in ("ok", "douteux"):
                    new = None
                if new is None:
                    c["dropped"] += 1
                    continue
                c["identical" if new == row["messages"][-1]["content"] else "changed"] += 1
                msgs = [*row["messages"][:-1], {"role": "assistant", "content": new}]
                if task == "detail":  # final/ garde le prompt d'entraînement de H3a ; K3 l'a resserré
                    msgs[0] = {"role": "system", "content": TRAIN_DETAILS_SYSTEM}
                kept.append({**row, "messages": msgs})
            with open(out / f"{f}.jsonl", "w", encoding="utf-8") as fh:
                fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in kept)
    return counts


def done_tids(path: Path) -> set[str]:
    return {r["tid"] for r in read_jsonl(path)} if path.exists() else set()


def cmd_build(args) -> None:
    tasks = build_tasks(Path(args.final), Path(args.hashes))
    with open(args.out, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(t, ensure_ascii=False) + "\n" for t in tasks)
    n: dict = {}
    for t in tasks:
        n[t["task"]] = n.get(t["task"], 0) + 1
    print(json.dumps({**n, "detail_k3_rejected": sum(t["k3_rejected"] for t in tasks)}))


def cmd_label(args) -> None:
    out = Path(args.out)
    seen = done_tids(out)
    todo = [t for t in read_jsonl(Path(args.tasks)) if t["task"] == args.task and t["tid"] not in seen]
    print(f"{args.task} : {len(todo)} à étiqueter", flush=True)
    with open(out, "a", encoding="utf-8") as f:
        for i, t in enumerate(todo, 1):
            t0 = time.time()
            try:
                raw = query_full(args.port, t["teacher_messages"], t["max_tokens"], args.timeout)["choices"][0]["message"]["content"]
                label, reason = clean_for(t["task"], raw)
            except Exception as e:  # noqa: BLE001
                raw, label, reason = "", None, f"erreur: {e!r}"
            f.write(json.dumps({"tid": t["tid"], "model": args.model_tag, "raw": raw, "label": label, "reason": reason,
                                "wall_s": round(time.time() - t0, 2)}, ensure_ascii=False) + "\n")
            f.flush()
            if i % 50 == 0:
                print(f"  {i}/{len(todo)}", flush=True)


def cmd_judge(args) -> None:
    judge_lib.URL = f"http://127.0.0.1:{args.port}/v1/chat/completions"
    tasks = {t["tid"]: t for t in read_jsonl(Path(args.tasks)) if t["k3_rejected"]}
    labels = {r["tid"]: r["label"] for r in read_jsonl(Path(args.labels)) if r["label"] and r["tid"] in tasks}
    out = Path(args.out)
    seen = done_tids(out)
    todo = [tid for tid in labels if tid not in seen]
    print(f"{len(todo)} étiquettes à juger (2 passes)", flush=True)
    with open(out, "a", encoding="utf-8") as f:
        for tid in todo:
            ctx = tasks[tid]["teacher_messages"][1]["content"]
            res = {}
            for p in ("A", "B"):
                try:
                    res[p] = judge_lib.call_judge(ctx, labels[tid], pass_id=p, timeout=args.timeout)["verdict"]
                except Exception:  # noqa: BLE001
                    res[p] = "erreur"
            final = ("invention" if res["A"] == res["B"] == "invention" else "douteux" if "invention" in res.values()
                     else "erreur" if "erreur" in res.values() else "ok")
            f.write(json.dumps({"tid": tid, "a": res["A"], "b": res["B"], "verdict": final}) + "\n")
            f.flush()


def cmd_assemble(args) -> None:
    tasks = read_jsonl(Path(args.tasks))
    labels = {r["tid"]: r["label"] for p in args.labels for r in read_jsonl(Path(p))}
    missing = [t["tid"] for t in tasks if t["tid"] not in labels]
    if missing:
        raise SystemExit(f"{len(missing)} tâches sans étiquette : étiquetage incomplet")
    verdicts = {r["tid"]: r["verdict"] for p in args.judge for r in read_jsonl(Path(p))}
    counts = assemble(Path(args.final), tasks, labels, verdicts, Path(args.out))
    print(json.dumps(counts, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build")
    s.add_argument("--final", required=True)
    s.add_argument("--hashes", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("label")
    s.add_argument("--tasks", required=True)
    s.add_argument("--task", required=True, choices=sorted(TASKS))
    s.add_argument("--port", type=int, required=True)
    s.add_argument("--model-tag", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--timeout", type=float, default=86400.0)
    s = sub.add_parser("judge")
    s.add_argument("--tasks", required=True)
    s.add_argument("--labels", required=True)
    s.add_argument("--port", type=int, required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--timeout", type=float, default=86400.0)
    s = sub.add_parser("assemble")
    s.add_argument("--final", required=True)
    s.add_argument("--tasks", required=True)
    s.add_argument("--labels", nargs="+", required=True)
    s.add_argument("--judge", nargs="*", default=[])
    s.add_argument("--out", required=True)
    args = ap.parse_args()
    {"build": cmd_build, "label": cmd_label, "judge": cmd_judge, "assemble": cmd_assemble}[args.cmd](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
