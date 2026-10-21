"""T9 : banc DEV v3 d'un modèle OpenRouter comme enseignant, sous garde-fou de dépense.

    python3 t9_bench.py subsample --harness dev.generic.json --n-fixtures 75 --seed 9 --out ids.txt
    python3 t9_bench.py run --harness dev.generic.json [--ids ids.txt] --model deepseek/deepseek-v4-flash \\
        --models-json models.json --ledger spend-bench.jsonl --cap 1.5 --out runs/<nom>.json

Entrée = harnais au format de production du profil generic (generic_harness.py : SUMMARY_SYSTEM
et bloc de faits L5, QA_SYSTEM et historique), c'est-à-dire le prompt d'étiquetage de l'enseignant
(x4_relabel.py envoie SUMMARY_SYSTEM sur le tour utilisateur du corpus). Réglages de label.py :
température 0, top_p 0,9 ; raisonnement coupé sauf --reasoning. La sortie a le format de
bench_run.py (`rows` : id, fixture, kind, out) et se note avec score_v3.py. Reprenable.
Le split TEST est refusé : il reste réservé à la décision finale des modèles de steph.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import openrouter_client as oc  # noqa: E402

GLOBAL_CAP = 5.0  # limite de la clé fixée par l'utilisateur ; les plafonds par poste sont dans les Ledger
MAX_TOKENS = {"summary": 90, "qa": 120}


def subsample(rows: list[dict], n_fixtures: int, seed: int) -> list[str]:
    """Fixtures tirées par famille au prorata (au moins une par famille), les deux langues de chacune."""
    by_family: dict[str, list[str]] = {}
    for r in rows:
        fx = by_family.setdefault(r["family"], [])
        if r["fixture"] not in fx:
            fx.append(r["fixture"])
    total = sum(len(v) for v in by_family.values())
    rng = random.Random(seed)
    chosen: set[str] = set()
    for fam in sorted(by_family):
        fx = sorted(by_family[fam])
        k = max(1, round(n_fixtures * len(fx) / total))
        chosen.update(rng.sample(fx, min(k, len(fx))))
    return [r["id"] for r in rows if r["fixture"] in chosen]


def params_for(reasoning: str) -> dict:
    p = {"temperature": 0, "top_p": 0.9, "provider": {"sort": "price"}}
    p["reasoning"] = {"enabled": False} if reasoning == "off" else {"effort": reasoning, "exclude": True}
    return p


def chat_retry(api, model: str, messages: list[dict], max_tokens: int, params: dict, tries: int = 3):
    """Réessaie les erreurs de transport (TLS, 429, 5xx) ; chaque échec reste compté par le Ledger."""
    for i in range(tries):
        try:
            return api.chat(model, messages, max_tokens, **params)
        except oc.BudgetExceeded:
            raise
        except oc.HTTPFailure as e:
            if i == tries - 1 or not (e.status == 429 or e.status >= 500):
                raise
        except OSError:
            if i == tries - 1:
                raise
        time.sleep(2 * (i + 1))
    raise AssertionError("inatteignable")


def run(args) -> None:
    if "test" in Path(args.harness).name:
        raise SystemExit("split TEST refusé")
    rows = json.load(open(args.harness, encoding="utf-8"))
    if args.ids:
        keep = set(Path(args.ids).read_text().split())
        rows = [r for r in rows if r["id"] in keep]
    out = Path(args.out)
    prev = json.load(open(out, encoding="utf-8"))["rows"] if out.exists() else []
    prev = [r for r in prev if r.get("out") is not None]
    done = {r["id"] for r in prev}
    todo = [r for r in rows if r["id"] not in done]
    prices = oc.load_prices(json.load(open(args.models_json))["data"])
    api = oc.OpenRouter(oc.read_key(), oc.Ledger(Path(args.ledger), args.cap), prices, timeout=args.timeout)
    usage = api.check_key(GLOBAL_CAP)
    print(f"{args.model} : {len(todo)} à faire, {len(done)} faits ; compte {usage:.4f} $, "
          f"phase {api.ledger.spent:.4f}/{args.cap} $", flush=True)
    params = params_for(args.reasoning)
    lock = threading.Lock()
    results = list(prev)
    cost = {"usd": 0.0, "errors": 0, "stopped": False}
    extra = args.reasoning_tokens if args.reasoning != "off" else 0

    def work(r: dict) -> None:
        if cost["stopped"]:
            return
        try:
            text, rec = chat_retry(api, args.model, r["messages"], MAX_TOKENS[r["kind"]] + extra, params)
            row = {"id": r["id"], "fixture": r["fixture"], "kind": r["kind"], "out": text, "cost": rec["cost"],
                   "prompt_n": rec["prompt_tokens"], "gen_n": rec["completion_tokens"],
                   "reasoning_n": rec.get("reasoning_tokens"), "provider": rec.get("provider"), "total": rec["wall_s"]}
        except oc.BudgetExceeded as e:
            cost["stopped"] = True
            print(f"ARRÊT plafond : {e}", flush=True)
            return
        except Exception as e:  # noqa: BLE001
            row = {"id": r["id"], "fixture": r["fixture"], "kind": r["kind"], "out": None, "error": repr(e)[:300]}
        with lock:
            results.append(row)
            cost["usd"] += row.get("cost") or 0
            cost["errors"] += row["out"] is None
            if len(results) % 25 == 0:
                save(out, args, results)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        list(ex.map(work, todo))
    save(out, args, results)
    print(json.dumps({"model": args.model, "rows": len(results), "errors": cost["errors"],
                      "run_cost_usd": round(cost["usd"], 6), "phase_spent_usd": round(api.ledger.spent, 6),
                      "stopped": cost["stopped"]}), flush=True)


def save(out: Path, args, results: list[dict]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    json.dump({"label": args.label or args.model, "model": args.model, "reasoning": args.reasoning,
               "harness": Path(args.harness).name, "rows": sorted(results, key=lambda r: r["id"])},
              open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tmp.replace(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("subsample")
    s.add_argument("--harness", required=True)
    s.add_argument("--n-fixtures", type=int, default=75)
    s.add_argument("--seed", type=int, default=9)
    s.add_argument("--out", required=True)
    s = sub.add_parser("run")
    s.add_argument("--harness", required=True)
    s.add_argument("--ids")
    s.add_argument("--model", required=True)
    s.add_argument("--label")
    s.add_argument("--models-json", required=True)
    s.add_argument("--ledger", required=True)
    s.add_argument("--cap", type=float, required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--parallel", type=int, default=8)
    s.add_argument("--timeout", type=float, default=120.0)
    s.add_argument("--reasoning", default="off", choices=["off", "minimal", "low", "medium"])
    s.add_argument("--reasoning-tokens", type=int, default=1500, help="jetons de sortie en plus si raisonnement")
    a = ap.parse_args()
    if a.cmd == "subsample":
        ids = subsample(json.load(open(a.harness, encoding="utf-8")), a.n_fixtures, a.seed)
        Path(a.out).write_text("\n".join(ids) + "\n")
        print(f"{len(ids)} évaluations")
    else:
        run(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
