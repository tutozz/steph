"""T9 : calibrage du juge A7 local (Qwen3.5 9B, 2 passes) contre l'enseignant OpenRouter, sur des réponses DEV.

    python3 t9_calibrate_a7.py --harness dev.generic.json --verdicts inv-a.json inv-b.json --n 200 \\
        --model ID --models-json models.json --ledger spend-judge.jsonl --cap 0.5 --out calib.json

Tirage : toutes les réponses que l'A7 marque « invention » ou « douteux », complétées au hasard (graine 9)
par des « ok » jusqu'à n. Référence : l'enseignant reçoit le même prompt A7 (judge_lib_a7, passe A) et
le même contexte (tour utilisateur du harnais). Précision et rappel de l'A7 sur les inventions, bruts et
repondérés par strate (la strate « ok » est sous-échantillonnée). DEV seulement.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import judge_lib_a7 as a7  # noqa: E402
import openrouter_client as oc  # noqa: E402

FLAGGED = ("invention", "douteux")


def sample(verdicts: list[dict], n: int, seed: int = 9) -> list[dict]:
    flagged = [v for v in verdicts if v["final"] in FLAGGED][:n]
    ok = [v for v in verdicts if v["final"] == "ok"]
    rng = random.Random(seed)
    return flagged + rng.sample(ok, min(len(ok), n - len(flagged)))


def _pr(tp: float, fp: float, fn: float) -> dict:
    return {"precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None,
            "tp": tp, "fp": fp, "fn": fn}


def metrics(rows: list[dict], population: dict[str, int], positive=("invention",)) -> dict:
    drawn: dict[str, int] = {}
    for r in rows:
        drawn[r["final"]] = drawn.get(r["final"], 0) + 1
    w = {k: population[k] / drawn[k] for k in drawn}
    raw = {"tp": 0.0, "fp": 0.0, "fn": 0.0}
    wt = {"tp": 0.0, "fp": 0.0, "fn": 0.0}
    for r in rows:
        pred, ref = r["final"] in positive, r["ref"] == "invention"
        k = "tp" if pred and ref else "fp" if pred else "fn" if ref else None
        if k:
            raw[k] += 1
            wt[k] += w[r["final"]]
    return {"raw": _pr(**raw), "weighted": _pr(**wt)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--harness", required=True)
    ap.add_argument("--verdicts", nargs="+", required=True)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--model", required=True)
    ap.add_argument("--models-json", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--cap", type=float, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if "test" in Path(a.harness).name:
        raise SystemExit("split TEST refusé")
    harness = {c["id"]: c for c in json.load(open(a.harness))}
    verdicts = [v for p in a.verdicts for v in json.load(open(p)) if v["final"] in (*FLAGGED, "ok")]
    population: dict[str, int] = {}
    for v in verdicts:
        population[v["final"]] = population.get(v["final"], 0) + 1
    chosen = sample(verdicts, a.n)
    prices = oc.load_prices(json.load(open(a.models_json))["data"])
    api = oc.OpenRouter(oc.read_key(), oc.Ledger(Path(a.ledger), a.cap), prices, timeout=180)
    print(f"{len(chosen)} verdicts ; compte {api.check_key(5.0):.4f} $, poste {api.ledger.spent:.4f}/{a.cap} $", flush=True)

    def ref(v: dict) -> dict:
        ctx = "\n\n".join(m["content"] for m in harness[v["id"]]["messages"] if m["role"] == "user")
        msgs = [{"role": "system", "content": a7.SYSTEM_PROMPT},
                {"role": "user", "content": a7.USER_TEMPLATE_A.format(context=ctx, phrase=v["phrase"])}]
        for _ in range(3):
            try:
                text, _rec = api.chat(a.model, msgs, 150, temperature=0, provider={"sort": "price"},
                                      reasoning={"enabled": False})
                parsed = a7._extract_json(text)
                inv = parsed.get("inventions", [])
                return {**v, "ref": "invention" if inv or parsed.get("verdict") == "invention" else "ok",
                        "ref_inventions": inv}
            except oc.BudgetExceeded:
                return {**v, "ref": "erreur"}  # plafond atteint : les verdicts déjà obtenus restent comptés
            except Exception:  # noqa: BLE001
                continue
        return {**v, "ref": "erreur"}

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(ref, chosen))
    rows = [r for r in rows if r["ref"] != "erreur"]
    rep = {"judge_ref": a.model, "n": len(rows), "population": population,
           "strict": metrics(rows, population, ("invention",)),
           "with_douteux": metrics(rows, population, FLAGGED),
           "phase_spent_usd": round(api.ledger.spent, 6)}
    json.dump({**rep, "rows": [{k: r[k] for k in ("id", "model_file", "phrase", "final", "ref", "ref_inventions")}
                               for r in rows]}, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: rep[k] for k in ("n", "population", "strict", "with_douteux")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
