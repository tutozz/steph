#!/usr/bin/env python3
"""Second score of bench v3, « juste et utile » : a strong judge (OpenRouter) grades each answer against
the raw output of the case on a fixed 0-100 scale (rungs 0, 25, 50, 75, 100), next to the facts score of
score_v3.py, which caps answers that keep another useful fact than the one the facts require.

    python3 judge_useful_v3.py controls --model M --models-json models.json --ledger spend.jsonl --cap 0.5 --out ctrl.json
    python3 judge_useful_v3.py run --ids ids.txt --model M --models-json models.json --ledger spend.jsonl --cap 0.5 \\
        --out verdicts.json run1.json [run2.json ...]
    python3 judge_useful_v3.py report --verdicts verdicts.json [--ids ids.txt] run1.json [...]

Context given to the judge: command, exit code and raw output of the case (cut in the middle beyond
6 000 characters), or the raw history and the question in the answer's language; never the bench
facts nor the reference. Identical answers to the same case are judged once across runs. 15 planted
answers (useful_controls.json, 3 per rung) check the judge before trusting it. DEV only, except
`--split test --decision-test`: candidates' TEST answers judged for an adoption decision (user decision of
2026-10-01), never to label training data; each such run leaves a zero-cost trace in the spend ledger.

SPDX-License-Identifier: MIT
"""

import argparse
import concurrent.futures
import json
import re
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "finetune"))
import openrouter_client as oc  # noqa: E402
from score_v3 import load_cases, parse_row_id  # noqa: E402

RUNGS = (0, 25, 50, 75, 100)
MAX_RAW = 6000  # coût : l'entrée domine le prix du juge ; 6 000 caractères couvrent la plupart des sorties DEV
LANG_NAME = {"fr": "français", "en": "anglais"}

SYSTEM = """Tu notes la réponse d'un assistant vocal de terminal pour une personne aveugle, qui l'entend au lieu de lire l'écran.
On te donne la commande, son code de sortie et sa sortie brute (ou un historique de session et une question), la langue attendue, puis la réponse. Choisis exactement un barreau de ce barème fixe :
100 : exacte, sans invention ; donne le fait clé dont la personne a besoin pour agir (le résultat principal ; ou l'erreur avec sa cause et son fichier ; ou la réponse à la question) ; assez courte pour l'oral.
75 : exacte et utile, fait clé présent, mais un détail utile manque, ou la phrase est plus longue ou plus lourde que nécessaire à l'oral.
50 : exacte, mais le fait clé manque : la personne sait seulement que ça a marché ou échoué, ou n'a qu'un détail secondaire, et doit relire la sortie.
25 : exacte mais presque inutile : ni résultat ni cause, recopie brute trop longue pour l'oral, ou réponse dans une autre langue que la langue attendue.
0 : fausse : au moins un fait inventé ou contraire à la sortie (nombre, nom, numéro de ligne, succès ou échec contraire au code de sortie), ou réponse vide.
Plusieurs réponses justes existent : ne pénalise pas un autre fait utile que celui que tu aurais choisi, tant que la personne peut agir. Le code de sortie décide du succès ou de l'échec. Pour une question dont la réponse n'est pas dans l'historique, « Pas dans l'historique » vaut 100 ; le dire quand la réponse y est vaut 50 au plus.
Réponds uniquement par ce JSON, sans texte autour :
{"note": 0, "invention": false, "raison": "<quelques mots>"}"""


def check_split(split, decision_test=False):
    if split == "dev" or (split == "test" and decision_test):
        return
    raise SystemExit("split TEST refusé : le juge « juste et utile » ne lit que le DEV, "
                     "sauf --split test --decision-test pour une décision")


def decision_trace(ledger, model, runs):
    ledger.settle(0.0, {"ts": round(time.time()), "event": "decision-test", "split": "test", "model": model,
                        "runs": [Path(p).name for p in runs], "cost": 0.0})


def cut(text, limit=MAX_RAW):
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    return text[:head] + "\n[… sortie coupée …]\n" + text[-(limit - head):]


def build_messages(case, lang, answer):
    if case["task"] == "qa":
        hist = "\n\n".join(f"[{i}] $ {h['cmd']}   (code {h['exit']})\n{cut(h['output_raw'], MAX_RAW // len(case['history']))}"
                           for i, h in enumerate(case["history"], 1))
        ctx = f"Historique de la session :\n{hist}\n\nQuestion : {case['question'][lang]}"
    else:
        ctx = f"Commande : {case['cmd']}\nCode de sortie : {case['exit']}\nSortie brute :\n{cut(case['output_raw'])}"
    user = f"{ctx}\n\nLangue attendue de la réponse : {LANG_NAME[lang]}\n\nRéponse à noter :\n{answer}"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def parse_note(text):
    m = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        d = None
    if not isinstance(d, dict) or d.get("note") not in RUNGS:
        return {"note": None, "invention": None, "raison": (text or "")[:200]}
    inv = bool(d.get("invention"))
    return {"note": 0 if inv else d["note"], "invention": inv, "raison": str(d.get("raison", ""))}


def controls_report(controls, notes):
    rep = {"n": len(controls), "exact": 0, "adjacent": 0, "errors": 0, "by_rung": {}}
    for c, n in zip(controls, notes):
        rep["by_rung"].setdefault(str(c["rung"]), []).append(n)
        if n is None:
            rep["errors"] += 1
            continue
        rep["exact"] += n == c["rung"]
        rep["adjacent"] += abs(n - c["rung"]) <= 25
    return rep


def mean(xs):
    return round(sum(xs) / len(xs), 1) if xs else None


def aggregate(rows, tasks):
    ok = [r for r in rows if r["note"] is not None]
    task = lambda r: tasks[parse_row_id(r["id"])[0]]  # noqa: E731
    return {"useful": mean([r["note"] for r in ok]),
            "fr": mean([r["note"] for r in ok if r["id"].endswith("@fr")]),
            "en": mean([r["note"] for r in ok if r["id"].endswith("@en")]),
            "summary": mean([r["note"] for r in ok if task(r) == "summary"]),
            "qa": mean([r["note"] for r in ok if task(r) == "qa"]),
            "inventions_pct": round(100 * sum(r["invention"] for r in ok) / len(ok), 1) if ok else None,
            "n": len(ok), "errors": len(rows) - len(ok)}


def make_api(a):
    prices = oc.load_prices(json.load(open(a.models_json))["data"])
    api = oc.OpenRouter(oc.read_key(), oc.Ledger(Path(a.ledger), a.cap), prices, timeout=180)
    print(f"compte {api.check_key(5.0):.4f} $, poste {api.ledger.spent:.4f}/{a.cap} $", flush=True)
    return api


def params(a):
    p = {"temperature": 0, "provider": {"sort": "price"}}
    p["reasoning"] = {"enabled": False} if a.reasoning == "off" else {"effort": a.reasoning, "exclude": True}
    return p


def ask(api, a, msgs):
    extra = 0 if a.reasoning == "off" else 2000
    for _ in range(3):
        try:
            text, rec = api.chat(a.model, msgs, 150 + extra, **params(a))
        except oc.BudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001
            text, rec = f"erreur {e!r}", {"cost": 0}
        v = parse_note(text)
        if v["note"] is not None:
            return {**v, "cost": rec["cost"]}
    return {**v, "cost": rec["cost"]}


def cmd_controls(a):
    cases = load_cases("dev")
    controls = json.loads((HERE / "useful_controls.json").read_text())
    api = make_api(a)
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda c: ask(api, a, build_messages(cases[c["case"]], c["lang"], c["answer"])), controls))
    rep = controls_report(controls, [r["note"] for r in res])
    json.dump({"judge": a.model, "reasoning": a.reasoning, "report": rep,
               "rows": [{**c, **r} for c, r in zip(controls, res)]}, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in rep.items()}, ensure_ascii=False))


def cmd_run(a):
    cases = load_cases(a.split)
    ids = set(Path(a.ids).read_text().split()) if a.ids else None
    out = Path(a.out)
    done = json.load(open(out)) if out.exists() else []
    done = [d for d in done if d["note"] is not None]
    seen = {(d["id"], d["answer"]) for d in done}
    todo, runs_of = [], {}
    for p in a.runs:
        for r in json.load(open(p))["rows"]:
            if r.get("out") is None or (ids is not None and r["id"] not in ids):
                continue
            cid, lang = parse_row_id(r["id"])
            if cid not in cases:
                raise SystemExit(f"{r['id']} : cas hors du split {a.split}")
            k = (r["id"], r["out"])
            runs_of.setdefault(k, []).append(Path(p).name)
            if k not in seen:
                seen.add(k)
                todo.append(k)
    api = make_api(a)
    if a.split == "test":
        decision_trace(api.ledger, a.model, a.runs)
    print(f"{len(todo)} réponses distinctes à juger", flush=True)
    lock = threading.Lock()
    stop = {"flag": False}

    def work(k):
        if stop["flag"]:
            return
        cid, lang = parse_row_id(k[0])
        try:
            v = ask(api, a, build_messages(cases[cid], lang, k[1]))
        except oc.BudgetExceeded as e:
            stop["flag"] = True
            print(f"ARRÊT plafond : {e}", flush=True)
            return
        with lock:
            done.append({"id": k[0], "answer": k[1], **v})
            if len(done) % 50 == 0:
                json.dump(done, open(out, "w"), ensure_ascii=False)

    with concurrent.futures.ThreadPoolExecutor(a.parallel) as ex:
        list(ex.map(work, todo))
    json.dump(done, open(out, "w"), ensure_ascii=False)
    print(json.dumps({"judged": len(done), "stopped": stop["flag"], "phase_spent_usd": round(api.ledger.spent, 6)}))


def cmd_report(a):
    cases = load_cases(a.split)
    tasks = {cid: c["task"] for cid, c in cases.items()}
    verdicts = {(v["id"], v["answer"]): v for v in json.load(open(a.verdicts))}
    ids = set(Path(a.ids).read_text().split()) if a.ids else None
    for p in a.runs:
        rows = []
        for r in json.load(open(p))["rows"]:
            if r.get("out") is None or (ids is not None and r["id"] not in ids):
                continue
            v = verdicts.get((r["id"], r["out"]), {"note": None, "invention": None})
            rows.append({"id": r["id"], "note": v["note"], "invention": v["invention"]})
        print(json.dumps({"file": Path(p).name, **aggregate(rows, tasks)}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("controls", "run"):
        s = sub.add_parser(name)
        s.add_argument("--model", required=True)
        s.add_argument("--models-json", required=True)
        s.add_argument("--ledger", required=True)
        s.add_argument("--cap", type=float, required=True)
        s.add_argument("--out", required=True)
        s.add_argument("--reasoning", default="off", choices=["off", "low", "medium"])
        s.add_argument("--split", default="dev")
    s = sub.choices["run"]
    s.add_argument("--ids")
    s.add_argument("--parallel", type=int, default=8)
    s.add_argument("--decision-test", action="store_true", help="autorise --split test pour juger une décision")
    s.add_argument("runs", nargs="+")
    s = sub.add_parser("report")
    s.add_argument("--verdicts", required=True)
    s.add_argument("--ids")
    s.add_argument("--split", default="dev")
    s.add_argument("--decision-test", action="store_true")
    s.add_argument("runs", nargs="+")
    a = ap.parse_args()
    check_split(a.split, getattr(a, "decision_test", False))
    {"controls": cmd_controls, "run": cmd_run, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
