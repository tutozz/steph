"""T9 : réétiquetage de data/final-x4-l5 par un enseignant OpenRouter, sur la machine qui porte le corpus.

    python3 t9_relabel.py build    --final DIR --qa data/final/qa_train.jsonl --out tasks.jsonl
    python3 t9_relabel.py label    --tasks tasks.jsonl --model ID --models-json models.json \\
                                   --ledger spend-relabel.jsonl --cap 2.5 --out labels.jsonl [--parallel 8]
    python3 t9_relabel.py assemble --final DIR --qa data/final/qa_train.jsonl --tasks tasks.jsonl \\
                                   --labels labels.jsonl --out data/final-t9

Mêmes prompts d'enseignant que X4 (x4_relabel.TASKS) : SUMMARY_SYSTEM(_EN) sur le tour utilisateur
de la ligne (bloc de faits L5 compris), PROGRESS_SYSTEM, TEACHER_DETAILS_SYSTEM ; questions : préfixe
de production de la ligne (qa_corpus). Mêmes nettoyages et plafonds de mots que X4. Ordre : résumés FR,
EN, questions, progression et flux, détail ; au plafond de dépense, l'étiquetage s'arrête net et
`assemble` garde l'étiquette X4 des lignes restantes (champ `label_source`). Une question « absent »
garde la réponse canonique ; une réponse de l'enseignant qui s'abstient sur une question à réponse
présente est rejetée (qa_corpus.decide_label). Les fichiers écrits contiennent du texte de corpus et
restent sur la machine ; seuls des comptes sont imprimés.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import openrouter_client as oc  # noqa: E402
from qa_corpus import ABSTENTION_PREFIXES, clean_answer  # noqa: E402
from t9_bench import GLOBAL_CAP, chat_retry, params_for  # noqa: E402
from x4_relabel import TASKS, clean_for  # noqa: E402

PRIORITY = ["fr_summary", "en_summary", "qa", "progress", "detail"]
QA_MAX_TOKENS = 100
README_NOTE = ("\nT9 : étiquettes réécrites par un enseignant OpenRouter (t9_relabel.py) ; champ label_source "
               "= t9 ou x4 (étiquette X4 gardée : rejet du nettoyage, abstention, plafond de dépense) ; "
               "qa_train.jsonl ajouté depuis data/final. Voir bench/matrix/results/t9/T9.md.\n")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def file_task() -> dict[str, str]:
    return {f: task for task, (files, _, _) in TASKS.items() for f in files}


def row_key(task: str, row: dict) -> str | None:
    """Clé de la requête d'enseignant d'une ligne ; None : la ligne garde son étiquette sans requête."""
    if task == "qa":
        return None if row.get("_category") == "absent" else sha(json.dumps(row["messages"][:-1], ensure_ascii=False))
    return sha(row["messages"][1]["content"])


def build_tasks(final: Path, qa: Path | None) -> list[dict]:
    tasks, seen = [], set()
    by_file = file_task()
    sources = [(p, by_file.get(p.name[:-len(".jsonl")])) for p in sorted(final.glob("*.jsonl"))]
    if qa is not None:
        sources.append((qa, "qa"))
    for path, task in sources:
        if task is None:
            continue
        for row in read_jsonl(path):
            key = row_key(task, row)
            if key is None or (task, key) in seen:
                continue
            seen.add((task, key))
            if task == "qa":
                msgs, max_tokens = row["messages"][:-1], QA_MAX_TOKENS
            else:
                _, system, max_tokens = TASKS[task]
                msgs = [{"role": "system", "content": system}, {"role": "user", "content": row["messages"][1]["content"]}]
            tasks.append({"tid": f"{task}:{key[:16]}", "task": task, "key": key, "max_tokens": max_tokens,
                          "teacher_messages": msgs})
    return tasks


def prioritized(tasks: list[dict]) -> list[dict]:
    return sorted(tasks, key=lambda t: PRIORITY.index(t["task"]))


def clean_label(task: str, raw: str) -> tuple[str | None, str]:
    if task == "qa":
        text, reason = clean_answer(raw)
        if text is not None and any(p in text.lower() for p in ABSTENTION_PREFIXES):
            return None, "abstention"
        return text, reason
    return clean_for(task, raw)


def assemble(final: Path, qa: Path | None, tasks: list[dict], labels: dict[str, dict], out: Path) -> dict:
    by_key = {(t["task"], t["key"]): t["tid"] for t in tasks}
    by_file = file_task()
    out.mkdir(parents=True, exist_ok=True)
    counts: dict = {}
    sources = [(p, by_file.get(p.name[:-len(".jsonl")])) for p in sorted(final.glob("*.jsonl"))]
    if qa is not None:
        sources.append((qa, "qa"))
    for path, task in sources:
        rows = read_jsonl(path)
        kept = []
        c = counts.setdefault(task or "untouched", {"rows": 0, "t9": 0, "kept_x4": 0, "rejected": 0, "unlabeled": 0})
        for row in rows:
            c["rows"] += 1
            key = row_key(task, row) if task else None
            tid = by_key.get((task, key)) if key else None
            lab = labels.get(tid) if tid else None
            if lab is not None and task == "qa" and lab.get("label") is not None:
                lab = {**lab, "label": clean_label("qa", lab["label"])[0]}
            if tid and lab is None:
                c["unlabeled"] += 1
            if lab is not None and lab.get("label") is None:
                c["rejected"] += 1
            if lab is not None and lab.get("label") is not None:
                msgs = [*row["messages"][:-1], {"role": "assistant", "content": lab["label"]}]
                kept.append({**row, "messages": msgs, "label_source": "t9"})
                c["t9"] += 1
            else:
                kept.append({**row, "label_source": "x4"})
                c["kept_x4"] += 1
        with open(out / path.name, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in kept)
    readme = final / "README.txt"
    note = readme.read_text(encoding="utf-8") if readme.exists() else ""
    (out / "README.txt").write_text(note + README_NOTE, encoding="utf-8")
    sums = [f"{sha_file(p)}  {p.name}\n" for p in sorted(out.glob("*.jsonl"))]
    (out / "SHA256SUMS").write_text("".join(sums))
    return counts


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_label(args) -> None:
    out = Path(args.out)
    done = {r["tid"] for r in read_jsonl(out)} if out.exists() else set()
    todo = [t for t in prioritized(read_jsonl(Path(args.tasks))) if t["tid"] not in done]
    if args.only:
        todo = [t for t in todo if t["task"] in args.only]
    prices = oc.load_prices(json.load(open(args.models_json))["data"])
    api = oc.OpenRouter(oc.read_key(Path(args.key)), oc.Ledger(Path(args.ledger), args.cap), prices, timeout=args.timeout)
    print(f"{len(todo)} à étiqueter, {len(done)} faits ; compte {api.check_key(GLOBAL_CAP):.4f} $, "
          f"poste {api.ledger.spent:.4f}/{args.cap} $", flush=True)
    params = params_for("off")
    lock = threading.Lock()
    state = {"n": 0, "stopped": False, "by": {}}
    fh = open(out, "a", encoding="utf-8")

    def work(t: dict) -> None:
        if state["stopped"]:
            return
        try:
            raw, rec = chat_retry(api, args.model, t["teacher_messages"], t["max_tokens"], params)
            label, reason = clean_label(t["task"], raw)
            cost = rec["cost"]
        except oc.BudgetExceeded as e:
            state["stopped"] = True
            print(f"ARRÊT plafond : {e}", flush=True)
            return
        except Exception as e:  # noqa: BLE001
            with lock:
                state["by"].setdefault("erreur", 0)
                state["by"]["erreur"] += 1
            print(f"erreur {t['tid']} : {repr(e)[:120]}", flush=True)
            return
        with lock:
            fh.write(json.dumps({"tid": t["tid"], "task": t["task"], "model": args.model, "raw": raw, "label": label,
                                 "reason": reason, "cost": cost}, ensure_ascii=False) + "\n")
            fh.flush()
            state["n"] += 1
            state["by"][reason] = state["by"].get(reason, 0) + 1
            if state["n"] % 200 == 0:
                try:
                    usage = api.check_key(GLOBAL_CAP)
                except oc.BudgetExceeded as e:
                    state["stopped"] = True
                    print(f"ARRÊT compte : {e}", flush=True)
                    return
                print(f"  {state['n']}/{len(todo)} ; poste {api.ledger.spent:.4f} $ ; compte {usage:.4f} $", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        list(ex.map(work, todo))
    fh.close()
    print(json.dumps({"labeled": state["n"], "reasons": state["by"], "stopped": state["stopped"],
                      "phase_spent_usd": round(api.ledger.spent, 6)}), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build")
    s.add_argument("--final", required=True)
    s.add_argument("--qa")
    s.add_argument("--out", required=True)
    s = sub.add_parser("label")
    s.add_argument("--tasks", required=True)
    s.add_argument("--model", required=True)
    s.add_argument("--models-json", required=True)
    s.add_argument("--ledger", required=True)
    s.add_argument("--cap", type=float, required=True)
    s.add_argument("--key", default=str(oc.KEY_PATH))
    s.add_argument("--out", required=True)
    s.add_argument("--only", nargs="*")
    s.add_argument("--parallel", type=int, default=8)
    s.add_argument("--timeout", type=float, default=120.0)
    s = sub.add_parser("assemble")
    s.add_argument("--final", required=True)
    s.add_argument("--qa")
    s.add_argument("--tasks", required=True)
    s.add_argument("--labels", required=True)
    s.add_argument("--out", required=True)
    a = ap.parse_args()
    qa = Path(a.qa) if getattr(a, "qa", None) else None
    if a.cmd == "build":
        tasks = build_tasks(Path(a.final), qa)
        with open(a.out, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(t, ensure_ascii=False) + "\n" for t in tasks)
        n: dict = {}
        for t in tasks:
            n[t["task"]] = n.get(t["task"], 0) + 1
        print(json.dumps(n))
    elif a.cmd == "label":
        cmd_label(a)
    else:
        labels = {r["tid"]: r for r in read_jsonl(Path(a.labels))}
        print(json.dumps(assemble(Path(a.final), qa, read_jsonl(Path(a.tasks)), labels, Path(a.out)), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
