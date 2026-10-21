#!/usr/bin/env python3
"""Audit of bench v3 facts by a strong judge (OpenRouter), DEV only: facts too strict, too lax, wrong
reference, and proposed alternative facts. Nothing in cases/ is modified: proposals go to a JSONL file
for human review.

    python3 propose_facts_v3.py --runs dev-a.json dev-b.json --n 100 --model M --models-json models.json \\
        --ledger spend.jsonl --cap 0.5 --out facts-proposals.jsonl --summary facts-audit.json

Cases: the DEV cases where the given runs lose the most facts points (at most 8 per family). The judge
sees the command, exit code, raw output, reference, facts (need, never) and the runs' answers with their
score and missed facts. A proposal either adds alternative patterns to a need fact (one of them is
enough), merges need facts into one group of alternatives, replaces or drops a fact, adds a never fact,
or fixes the reference. Every proposal is checked here: patterns compile, the reference still scores 1,
and the runs' answers are rescored before and after.

SPDX-License-Identifier: MIT
"""

import argparse
import concurrent.futures
import copy
import json
import re
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "finetune"))
import openrouter_client as oc  # noqa: E402
from judge_useful_v3 import cut  # noqa: E402
from score_v3 import load_cases, parse_row_id, score_answer  # noqa: E402

ACTIONS = {"add_alternatives", "merge_with", "replace", "drop", "add_never", "fix_reference"}

SYSTEM = """Tu audites les faits de notation d'un banc pour un assistant vocal de terminal destiné à des personnes aveugles : une réponse courte (une phrase, 15 à 20 mots) doit dire l'essentiel d'une sortie de commande.
Notation : la réponse passe en minuscules sans accents ; chaque fait « need » est une liste d'expressions régulières Python par langue, et UNE seule correspondance suffit pour ce fait ; la note est la part des faits need trouvés ; un fait « never » trouvé met la note à 0.
Défauts à chercher :
- trop_strict : une réponse juste et utile perd des points parce qu'elle a retenu un autre fait utile (le point-virgule manquant sans le numéro de ligne, la perte de 100 % sans le nom d'hôte, le code d'erreur au lieu du message) ou une autre formulation ;
- trop_laxiste : une réponse fausse ou inutile obtient tous les points ;
- reference_fausse : la réponse de référence contredit la sortie.
Pour un fait trop strict, propose un groupe de variantes acceptées (ajout d'expressions au fait, ou fusion de deux faits en un seul groupe « l'hôte OU le code »), en gardant exigé ce qui est vraiment essentiel pour que la personne puisse agir. N'élargis pas au point qu'une réponse vague passe. Écris les expressions pour du texte en minuscules sans accents, dans les deux langues.
Actions possibles : add_alternatives (fact_id, fr, en : expressions ajoutées), merge_with (fact_id, merge : autres fact_id fusionnés en un groupe), replace (fact_id, fr, en), drop (fact_id), add_never (fr, en), fix_reference (fr, en : nouvelle référence).
Réponds uniquement par ce JSON :
{"diagnostic": "ok|trop_strict|trop_laxiste|reference_fausse", "proposals": [{"action": "...", "fact_id": "...", "merge": [], "fr": [], "en": [], "essential": "<ce qui reste exigé>", "justification": "<une phrase>"}]}
Si les faits sont bons, diagnostic ok et proposals vide."""


def _need(case):
    return case["facts"]["need"]


def apply_proposal(case, prop):
    new = copy.deepcopy(case)
    need = _need(new)
    ids = [f["id"] for f in need]
    act = prop["action"]
    if act == "fix_reference":
        new["reference"] = {"fr": prop["fr"], "en": prop["en"]} if isinstance(prop["fr"], str) else \
            {"fr": prop["fr"][0], "en": prop["en"][0]}
        return new
    if act == "add_never":
        new["facts"]["never"].append({"id": "t9-never", "fr": list(prop["fr"]), "en": list(prop["en"])})
        return new
    if prop.get("fact_id") not in ids:
        raise ValueError(f"fait inconnu : {prop.get('fact_id')}")
    i = ids.index(prop["fact_id"])
    if act == "add_alternatives":
        need[i]["fr"] = need[i]["fr"] + list(prop["fr"])
        need[i]["en"] = need[i]["en"] + list(prop["en"])
    elif act == "replace":
        need[i]["fr"], need[i]["en"] = list(prop["fr"]), list(prop["en"])
    elif act == "drop":
        del need[i]
    elif act == "merge_with":
        others = [f for f in need if f["id"] in prop["merge"]]
        if len(others) != len(prop["merge"]):
            raise ValueError(f"fusion avec un fait inconnu : {prop['merge']}")
        group = {"id": "+".join([need[i]["id"], *[f["id"] for f in others]]),
                 "fr": need[i]["fr"] + [p for f in others for p in f["fr"]],
                 "en": need[i]["en"] + [p for f in others for p in f["en"]]}
        new["facts"]["need"] = [group if f is need[i] else f for f in need if f["id"] not in prop["merge"]]
    else:
        raise ValueError(f"action inconnue : {act}")
    return new


def check(case, prop, answers):
    res = {"regex_ok": True, "reference_passes": None, "before": [], "after": [], "newly_full": 0, "error": None}
    try:
        for p in list(prop.get("fr") or []) + list(prop.get("en") or []):
            if prop["action"] != "fix_reference":
                re.compile(p)
        new = apply_proposal(case, prop)
        if not new["facts"]["need"]:
            raise ValueError("plus aucun fait need")
        res["reference_passes"] = all(score_answer(new, lg, new["reference"][lg]) == 1.0 for lg in ("fr", "en"))
        res["before"] = [round(score_answer(case, a["lang"], a["out"]), 3) for a in answers]
        res["after"] = [round(score_answer(new, a["lang"], a["out"]), 3) for a in answers]
        res["newly_full"] = sum(b < 1.0 <= a for b, a in zip(res["before"], res["after"]))
    except (re.error, ValueError, KeyError, TypeError, IndexError) as e:
        res["regex_ok"] = not isinstance(e, re.error)
        res["error"] = repr(e)[:200]
    return res


def select_cases(per_case_list, family, n, per_family=8):
    loss = {}
    for per in per_case_list:
        for rid, s in per.items():
            cid = parse_row_id(rid)[0]
            loss[cid] = loss.get(cid, 0.0) + (1.0 - s)
    ranked = sorted((c for c in loss if loss[c] > 0), key=lambda c: (-loss[c], c))
    out, count = [], {}
    for c in ranked:
        if count.get(family[c], 0) >= per_family:
            continue
        count[family[c]] = count.get(family[c], 0) + 1
        out.append(c)
        if len(out) == n:
            break
    return out


def missed(case, lang, out):
    from score import clean, plain
    text = plain(clean(out))
    return [f["id"] for f in _need(case) if not any(re.search(p, text) for p in f[lang])]


def build_user(case, answers):
    if case["task"] == "qa":
        ctx = "\n\n".join(f"[{i}] $ {h['cmd']}   (code {h['exit']})\n{cut(h['output_raw'], 12000 // len(case['history']))}"
                          for i, h in enumerate(case["history"], 1))
        ctx = f"Historique :\n{ctx}\n\nQuestion : {json.dumps(case['question'], ensure_ascii=False)}"
    else:
        ctx = f"Commande : {case['cmd']}\nCode de sortie : {case['exit']}\nSortie brute :\n{cut(case['output_raw'])}"
    ans = "\n".join(f"- [{a['lang']}] {a['run']} : « {a['out']} » -> note {a['score']:.2f}, faits manqués : {a['missed']}"
                    for a in answers)
    return (f"{ctx}\n\nRéférence : {json.dumps(case['reference'], ensure_ascii=False)}\n"
            f"Faits : {json.dumps(case['facts'], ensure_ascii=False)}\nMots maximum : {case['max_words']}\n\n"
            f"Réponses de modèles forts :\n{ans}")


def parse(text):
    m = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict) or "diagnostic" not in d:
        return None
    d["proposals"] = [p for p in d.get("proposals") or [] if isinstance(p, dict) and p.get("action") in ACTIONS]
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--model", required=True)
    ap.add_argument("--reasoning", default="low", choices=["off", "low", "medium"])
    ap.add_argument("--models-json", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--cap", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--resume", action="store_true", help="ne relance que les cas en erreur des fichiers existants")
    a = ap.parse_args()
    cases = load_cases("dev")
    runs = {Path(p).name: {r["id"]: r["out"] for r in json.load(open(p))["rows"] if r.get("out") is not None}
            for p in a.runs}
    per = [{rid: score_answer(cases[parse_row_id(rid)[0]], parse_row_id(rid)[1], out) for rid, out in rows.items()}
           for rows in runs.values()]
    chosen = select_cases(per, {c: v["family"] for c, v in cases.items()}, a.n)
    prices = oc.load_prices(json.load(open(a.models_json))["data"])
    api = oc.OpenRouter(oc.read_key(), oc.Ledger(Path(a.ledger), a.cap), prices, timeout=300)
    print(f"{len(chosen)} cas ; compte {api.check_key(5.0):.4f} $, poste {api.ledger.spent:.4f}/{a.cap} $", flush=True)
    params = {"temperature": 0, "provider": {"sort": "price"},
              "reasoning": {"enabled": False} if a.reasoning == "off" else {"effort": a.reasoning, "exclude": True}}
    lock = threading.Lock()
    lines, summary = [], {}
    if a.resume and Path(a.summary).exists():
        summary = {c: v for c, v in json.load(open(a.summary))["per_case"].items() if v["diagnostic"] != "erreur"}
        lines = [json.loads(x) for x in open(a.out, encoding="utf-8") if x.strip()]
        chosen = [c for c in chosen if c not in summary]
        print(f"reprise : {len(chosen)} cas en erreur relancés", flush=True)

    def work(cid):
        case = cases[cid]
        answers = [{"run": name, "lang": lg, "out": rows[f"{cid}@{lg}"],
                    "score": score_answer(case, lg, rows[f"{cid}@{lg}"]), "missed": missed(case, lg, rows[f"{cid}@{lg}"])}
                   for name, rows in runs.items() for lg in ("fr", "en") if f"{cid}@{lg}" in rows]
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": build_user(case, answers)}]
        d = None
        for _ in range(2):
            try:
                text, _rec = api.chat(a.model, msgs, 6000 if a.reasoning != "off" else 1200, **params)
            except oc.BudgetExceeded as e:
                print(f"ARRÊT plafond : {e}", flush=True)
                return
            except Exception as e:  # noqa: BLE001
                text = repr(e)
            d = parse(text)
            if d is not None:
                break
        with lock:
            if d is None:
                summary[cid] = {"diagnostic": "erreur"}
                return
            summary[cid] = {"diagnostic": d["diagnostic"], "proposals": len(d["proposals"]), "family": case["family"]}
            for p in d["proposals"]:
                lines.append({"case": cid, "family": case["family"], "task": case["task"], "diagnostic": d["diagnostic"],
                              "proposal": p, "check": check(case, p, answers),
                              "answers": [{k: x[k] for k in ("run", "lang", "out")} for x in answers], "judge": a.model})

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        list(ex.map(work, chosen))
    lines.sort(key=lambda x: x["case"])
    with open(a.out, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in lines)
    diag = {}
    for v in summary.values():
        diag[v["diagnostic"]] = diag.get(v["diagnostic"], 0) + 1
    usable = [x for x in lines if x["check"]["regex_ok"] and x["check"]["reference_passes"]]
    json.dump({"judge": a.model, "cases": len(chosen), "diagnostics": diag, "proposals": len(lines),
               "proposals_checked_ok": len(usable), "newly_full_answers": sum(x["check"]["newly_full"] for x in usable),
               "per_case": summary, "phase_spent_usd": round(api.ledger.spent, 6)},
              open(a.summary, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"cases": len(chosen), "diagnostics": diag, "proposals": len(lines), "checked_ok": len(usable)}))


if __name__ == "__main__":
    main()
