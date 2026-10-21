"""X4a : audit de l'étiquetage de l'enseignant Qwen3.5 9B, comparaison avec un plus gros étiqueteur.

Tourne sur la machine qui porte le corpus (xeon, data/final/) ; les fichiers écrits contiennent du
texte de corpus et y restent. Seule la sous-commande `counts` produit ce qui peut revenir au dépôt :
des comptes agrégés, sans texte.

    python3 x4a_audit.py sample --final DIR --hashes DIR --out sample.jsonl
    python3 x4a_audit.py label  --sample sample.jsonl --port 8950 --model-tag 27b --out labels-27b.jsonl
    python3 x4a_audit.py judge  --sample sample.jsonl --labels labels-27b.jsonl --port 8951 \\
        --judge-tag j9 --out j9-on-27b.jsonl
    python3 x4a_audit.py counts --sample sample.jsonl --labels labels-*.jsonl --judges j*.jsonl

Prompts de l'enseignant : ceux de l'étiquetage d'origine (label.py : prompt de production du résumé ;
label_features.py : TEACHER_DETAILS_SYSTEM pour le détail resserré en K3, prompt de production pour
début et progression ; qa_corpus.py : préfixe QA de production). Requête identique à label.query().

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import judge_lib  # noqa: E402
from label import judge as clean_summary  # noqa: E402
from label_features import TEACHER_DETAILS_SYSTEM, judge as clean_feature  # noqa: E402
from qa_corpus import clean_answer  # noqa: E402

from steph.prompts import PROGRESS_SYSTEM, START_SYSTEM, SUMMARY_SYSTEM, SUMMARY_SYSTEM_EN  # noqa: E402

FR_SUMMARY = ["macos", "linux-low", "linux-dev", "snapshot-linux-dev", "snapshot-linux-low"]
EN_SUMMARY = ["macos.en", "linux-low.en"]
# stratum: (files, random size, extra judge rejects, stored verdict source, max_tokens)
STRATA = {
    "fr_summary": (FR_SUMMARY, 60, 10, "a11", 64),
    "en_summary": (EN_SUMMARY, 40, 6, "en", 64),
    "detail": (["detail"], 40, 10, "k3", 120),
    "start": (["start"], 30, 0, "h3a", 120),
    "progress": (["progress"], 30, 0, "h3a", 120),
    "qa": (["qa_train"], 30, 0, None, 100),
}
FEATURE_WORDS = {"detail": 60, "start": 10, "progress": 12}
SYSTEMS = {"fr_summary": SUMMARY_SYSTEM, "en_summary": SUMMARY_SYSTEM_EN, "detail": TEACHER_DETAILS_SYSTEM,
           "start": START_SYSTEM, "progress": PROGRESS_SYSTEM}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def teacher_messages(stratum: str, row: dict) -> list[dict]:
    if stratum == "qa":  # préfixe de production déjà dans la ligne, dernière réponse retirée
        return row["messages"][:-1]
    return [{"role": "system", "content": SYSTEMS[stratum]}, {"role": "user", "content": row["messages"][1]["content"]}]


def cmd_sample(args) -> None:
    final, hashes = Path(args.final), Path(args.hashes)
    verdicts: dict[tuple[str, str], str] = {}
    for line in open(hashes / "verdicts.jsonl"):
        v = json.loads(line)
        verdicts[(v["src"], v["sha"])] = v["v"]
    applied = {"a11": set((hashes / "fr-a11.txt").read_text().split()),
               "en": set((hashes / "en-reviewed.txt").read_text().split()),
               "k3": set((hashes / "detail-k3.txt").read_text().split()),
               "h3a": set((hashes / "h3a-start.txt").read_text().split())}
    k3_all = set((hashes / "detail-k3-all.txt").read_text().split())
    rng = random.Random(args.seed)
    out = []
    for stratum, (files, n, n_extra, vsrc, max_tokens) in STRATA.items():
        pool: dict[str, dict] = {}
        for f in files:
            for line in open(final / f"{f}.jsonl", encoding="utf-8"):
                row = json.loads(line)
                h = sha(row["messages"][1]["content"])
                if stratum == "detail" and h not in k3_all:
                    continue  # le détail entraîné est celui réétiqueté en K3
                pool.setdefault(h, row)
        keys = sorted(pool)
        drawn = rng.sample(keys, n)
        rejected = [h for h in keys if vsrc and verdicts.get((vsrc, h)) == "invention" and h not in drawn]
        extra = rng.sample(sorted(rejected), min(n_extra, len(rejected)))
        for h, is_extra in [(h, False) for h in drawn] + [(h, True) for h in extra]:
            row = pool[h]
            out.append({"sid": f"{stratum}:{len(out)}", "stratum": stratum, "extra": is_extra, "sha": h,
                        "source": row["source"], "category": row.get("_category"),
                        "lang": "en" if stratum == "en_summary" else "fr",
                        "stored_verdict": verdicts.get((vsrc, h), "ok" if stratum == "qa" else None),
                        "stored_rejected": bool(vsrc) and h in applied.get(vsrc, set()),
                        "max_tokens": max_tokens, "teacher_messages": teacher_messages(stratum, row),
                        "stored_label": None if stratum == "detail" else row["messages"][-1]["content"]})
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(collections.Counter(f"{r['stratum']}{'+extra' if r['extra'] else ''}" for r in out)))


def query_full(port: int, messages: list[dict], max_tokens: int, timeout: float) -> dict:
    """Corps identique à label.query() ; renvoie aussi usage et timings du serveur."""
    body = json.dumps({
        "messages": messages, "max_tokens": max_tokens, "temperature": 0, "top_p": 0.9,
        "presence_penalty": 1.0, "stream": False, "cache_prompt": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", body,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def clean_for(stratum: str, raw: str) -> tuple[str | None, str]:
    if stratum in ("fr_summary", "en_summary"):
        return clean_summary(raw)
    if stratum == "qa":
        return clean_answer(raw)
    return clean_feature(raw, FEATURE_WORDS[stratum], stratum)


def done_sids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(l)["sid"] for l in open(path, encoding="utf-8") if l.strip()}


def cmd_label(args) -> None:
    rows = [json.loads(l) for l in open(args.sample, encoding="utf-8")]
    out = Path(args.out)
    seen = done_sids(out)
    todo = [r for r in rows if r["sid"] not in seen]
    print(f"{len(rows)} lignes, {len(todo)} à étiqueter", flush=True)
    with open(out, "a", encoding="utf-8") as f:
        for i, r in enumerate(todo, 1):
            t0 = time.time()
            try:
                data = query_full(args.port, r["teacher_messages"], r["max_tokens"], args.timeout)
                raw = data["choices"][0]["message"]["content"]
                label, reason = clean_for(r["stratum"], raw)
                usage, timings = data.get("usage", {}), data.get("timings", {})
            except Exception as e:  # noqa: BLE001
                raw, label, reason, usage, timings = "", None, f"erreur: {e!r}", {}, {}
            f.write(json.dumps({"sid": r["sid"], "model": args.model_tag, "raw": raw, "label": label,
                                "reason": reason, "wall_s": round(time.time() - t0, 2),
                                "t0": round(t0, 1), "t1": round(time.time(), 1),
                                "prompt_tokens": usage.get("prompt_tokens"),
                                "completion_tokens": usage.get("completion_tokens"),
                                "prompt_ms": timings.get("prompt_ms"), "predicted_ms": timings.get("predicted_ms")},
                               ensure_ascii=False) + "\n")
            f.flush()
            if i % 10 == 0:
                print(f"  {i}/{len(todo)}", flush=True)


def cmd_judge(args) -> None:
    judge_lib.URL = f"http://127.0.0.1:{args.port}/v1/chat/completions"
    rows = {}
    for line in open(args.sample, encoding="utf-8"):
        r = json.loads(line)
        rows[r["sid"]] = r
    if args.labels == "stored":
        labels = {sid: r["stored_label"] for sid, r in rows.items() if r["stored_label"] is not None}
    else:
        labels = {}
        for line in open(args.labels, encoding="utf-8"):
            lab = json.loads(line)
            if lab["label"]:
                labels[lab["sid"]] = lab["label"]
    out = Path(args.out)
    seen = done_sids(out)
    todo = [sid for sid in labels if sid not in seen and (not args.strata or rows[sid]["stratum"] in args.strata)]
    print(f"{len(todo)} étiquettes à juger (2 passes)", flush=True)
    with open(out, "a", encoding="utf-8") as f:
        for i, sid in enumerate(todo, 1):
            ctx = rows[sid]["teacher_messages"][1]["content"]
            t0 = time.time()
            res = {}
            for p in ("A", "B"):
                try:
                    res[p] = judge_lib.call_judge(ctx, labels[sid], pass_id=p, timeout=args.timeout)
                except Exception as e:  # noqa: BLE001
                    res[p] = {"verdict": "erreur", "inventions": [], "_error": repr(e)}
            va, vb = res["A"]["verdict"], res["B"]["verdict"]
            final = ("invention" if va == vb == "invention" else "douteux" if "invention" in (va, vb)
                     else "erreur" if "erreur" in (va, vb) else "ok")
            f.write(json.dumps({"sid": sid, "judge": args.judge_tag, "a": va, "b": vb, "verdict": final,
                                "inventions": res["A"].get("inventions", []) + res["B"].get("inventions", []),
                                "wall_s": round(time.time() - t0, 2), "t0": round(t0, 1),
                                "t1": round(time.time(), 1)}, ensure_ascii=False) + "\n")
            f.flush()
            if i % 10 == 0:
                print(f"  {i}/{len(todo)}", flush=True)


def cmd_counts(args) -> None:
    """Comptes agrégés seulement : aucun texte de corpus ni d'étiquette n'est imprimé."""
    rows = {}
    for line in open(args.sample, encoding="utf-8"):
        r = json.loads(line)
        rows[r["sid"]] = r
    report: dict = {"sample": dict(collections.Counter(
        f"{r['stratum']}{'+extra' if r['extra'] else ''}" for r in rows.values()))}
    for p in args.labels:
        by: dict = collections.defaultdict(collections.Counter)
        model = None
        for line in open(p, encoding="utf-8"):
            lab = json.loads(line)
            model = lab["model"]
            s = by[rows[lab["sid"]]["stratum"]]
            s["n"] += 1
            s["rejected"] += lab["label"] is None
            s["wall_s"] += lab["wall_s"]
            s["prompt_tokens"] += lab["prompt_tokens"] or 0
            s["completion_tokens"] += lab["completion_tokens"] or 0
            s["identical_to_stored"] += lab["label"] is not None and lab["label"] == rows[lab["sid"]]["stored_label"]
        report[f"labels:{model}"] = {k: {**v, "wall_s": round(v["wall_s"], 1),
                                         "s_per_label": round(v["wall_s"] / v["n"], 2)} for k, v in by.items()}
    for p in args.judges:
        by = collections.defaultdict(collections.Counter)
        for line in open(p, encoding="utf-8"):
            j = json.loads(line)
            by[rows[j["sid"]]["stratum"]][j["verdict"]] += 1
            by[rows[j["sid"]]["stratum"]]["wall_s"] += j["wall_s"]
        report[f"judge:{Path(p).stem}"] = {k: {**v, "wall_s": round(v["wall_s"], 1)} for k, v in by.items()}
    print(json.dumps(report, ensure_ascii=False, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--final", required=True)
    s.add_argument("--hashes", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--seed", type=int, default=4)
    s = sub.add_parser("label")
    s.add_argument("--sample", required=True)
    s.add_argument("--port", type=int, required=True)
    s.add_argument("--model-tag", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--timeout", type=float, default=900.0)
    s = sub.add_parser("judge")
    s.add_argument("--sample", required=True)
    s.add_argument("--labels", required=True, help="fichier labels-*.jsonl, ou « stored »")
    s.add_argument("--port", type=int, required=True)
    s.add_argument("--judge-tag", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--strata", nargs="*", default=[])
    s.add_argument("--timeout", type=float, default=900.0)
    s = sub.add_parser("counts")
    s.add_argument("--sample", required=True)
    s.add_argument("--labels", nargs="*", default=[])
    s.add_argument("--judges", nargs="*", default=[])
    args = ap.parse_args()
    {"sample": cmd_sample, "label": cmd_label, "judge": cmd_judge, "counts": cmd_counts}[args.cmd](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
