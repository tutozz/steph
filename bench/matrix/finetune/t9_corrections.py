"""T9 : corrections ciblées. Les modèles de steph (v1.0, G3b) répondent sur des entrées du corpus
d'entraînement ; l'enseignant OpenRouter juge chaque réponse contre l'entrée que le modèle a lue et
la réécrit si elle invente, manque le fait clé ou s'abstient à tort. Sur la machine du corpus.

    python3 t9_corrections.py items --final data/final-x4-l5 --qa data/final/qa_train.jsonl --out items.jsonl
    python3 t9_corrections.py gen   --items items.jsonl --port 8932 --model-tag v1.0 --out gen-v1.0.jsonl
    python3 t9_corrections.py judge --items items.jsonl --gen gen-v1.0.jsonl gen-g3b.jsonl --model ID \\
        --models-json models.json --ledger spend-corrections.jsonl --cap 1.5 --out verdicts.jsonl
    python3 t9_corrections.py assemble --items items.jsonl --gen gen-*.jsonl --verdicts verdicts.jsonl \\
        --out data/final-t9-corrections

Entrées : résumés FR et EN de final-x4-l5 (dédoublonnés) et questions de data/final/qa_train.jsonl,
au format d'entraînement (prompt de la ligne, dernière réponse retirée), questions d'abord.
Génération au réglage de production (v3lib.PRODUCTION_PAYLOAD), graine 42. Sortie : pairs.jsonl
(prompt, réponse fautive, correction, verdict) et sft.jsonl (lignes corrigées), seulement les réponses
fautives. Les fichiers écrits contiennent du texte de corpus et restent sur la machine.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import openrouter_client as oc  # noqa: E402
from label import judge as clean_summary  # noqa: E402
from qa_corpus import ABSTENTION_PREFIXES, CANONICAL_ABSENT_BY_LANG, clean_answer  # noqa: E402
from t9_bench import GLOBAL_CAP, chat_retry, params_for  # noqa: E402

SUMMARY_FILES = {"macos": "fr", "linux-low": "fr", "linux-dev": "fr", "snapshot-linux-dev": "fr",
                 "snapshot-linux-low": "fr", "macos.en": "en", "linux-low.en": "en"}
PAYLOAD = {"summary": {"temperature": 0.2, "top_p": 0.9, "max_tokens": 90},
           "qa": {"temperature": 0.3, "top_p": 0.9, "max_tokens": 400}}
VERDICTS = {"ok", "invention", "manque", "abstention"}

JUDGE_SYSTEM = """Tu contrôles la réponse d'un petit modèle qui sert de voix à un terminal, pour une personne malvoyante qui écoute au lieu de lire.
On te donne la consigne que le modèle a reçue, l'entrée qu'il a lue (commande, statut et sortie ; ou historique de session puis question) et sa réponse. Juge la réponse contre cette entrée seulement.
Verdicts :
- invention : la réponse affirme un fait absent de l'entrée ou contraire à elle (nombre, nom, succès ou échec contraire au code de sortie, « ligne N » que l'entrée n'écrit pas, cause que l'entrée ne donne pas) ;
- manque : la réponse ne donne pas le fait clé que la personne doit entendre (le résultat principal ; l'erreur et son fichier ; la réponse à la question) alors qu'il est écrit dans l'entrée ;
- abstention : la réponse dit que l'information n'est pas dans l'historique alors qu'elle y est ;
- ok : tout le reste. Une autre formulation, un détail secondaire omis, un arrondi fidèle ou le style télégraphique ne sont pas des défauts.
Si le verdict n'est pas ok, écris la correction : la réponse que le modèle aurait dû donner, qui respecte exactement sa consigne (langue, longueur, style) et n'utilise que des faits écrits dans l'entrée. Si la réponse est ok, laisse la correction vide.
Réponds uniquement par ce JSON, sans texte autour :
{"verdict": "ok|invention|manque|abstention", "raison": "<quelques mots>", "correction": "<réponse corrigée, ou vide>"}"""

JUDGE_USER = """Consigne reçue par le modèle :
{system}

Entrée lue par le modèle :
{context}

Réponse du modèle :
{answer}"""


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def build_items(final: Path, qa: Path | None) -> list[dict]:
    items, seen = [], set()
    if qa is not None:
        for row in read_jsonl(qa):
            prompt = row["messages"][:-1]
            key = sha(json.dumps(prompt, ensure_ascii=False))
            if key not in seen:
                seen.add(key)
                items.append({"iid": f"qa:{key[:16]}", "task": "qa", "lang": "fr", "category": row.get("_category"),
                              "source_file": qa.name[:-len(".jsonl")], "prompt": prompt})
    for lang in ("fr", "en"):
        for stem in [s for s, lg in SUMMARY_FILES.items() if lg == lang]:
            path = final / f"{stem}.jsonl"
            if not path.exists():
                continue
            for row in read_jsonl(path):
                prompt = row["messages"][:2]
                key = sha(prompt[1]["content"])
                if key not in seen:
                    seen.add(key)
                    items.append({"iid": f"{lang}:{key[:16]}", "task": "summary", "lang": lang, "category": None,
                                  "source_file": stem, "prompt": prompt})
    return items


def parse_verdict(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        d = None
    if not isinstance(d, dict) or d.get("verdict") not in VERDICTS:
        return {"verdict": "erreur", "raison": (text or "")[:200], "correction": ""}
    return {"verdict": d["verdict"], "raison": str(d.get("raison", "")), "correction": str(d.get("correction") or "")}


def is_abstention(text: str) -> bool:
    return any(p in text.lower() for p in ABSTENTION_PREFIXES)


def make_pair(item: dict, model: str, answer: str, verdict: dict) -> dict | None:
    """Paire (réponse fautive, correction) ; None si la réponse est juste ou la correction inutilisable."""
    if verdict["verdict"] not in VERDICTS - {"ok"}:
        return None
    if item["task"] == "qa" and item["category"] == "absent":
        chosen = CANONICAL_ABSENT_BY_LANG[item["lang"]]
    else:
        cleaned = (clean_answer if item["task"] == "qa" else clean_summary)(verdict["correction"])[0]
        if cleaned is None or (item["task"] == "qa" and is_abstention(cleaned)):
            return None
        chosen = cleaned
    if chosen.strip() == answer.strip():
        return None
    return {"iid": item["iid"], "task": item["task"], "lang": item["lang"], "category": item["category"],
            "source_file": item["source_file"], "model": model, "verdict": verdict["verdict"],
            "raison": verdict.get("raison", ""), "prompt": item["prompt"], "rejected": answer, "chosen": chosen,
            "sft": {"source": f"t9-corr-{model}", "messages": [*item["prompt"], {"role": "assistant", "content": chosen}]}}


def judge_context(prompt: list[dict]) -> str:
    return "\n\n".join(m["content"] for m in prompt if m["role"] == "user")


def cmd_gen(args) -> None:
    items = read_jsonl(Path(args.items))
    if args.limit:
        items = items[:args.limit]
    out = Path(args.out)
    done = {r["iid"] for r in read_jsonl(out)} if out.exists() else set()
    todo = [i for i in items if i["iid"] not in done]
    print(f"{args.model_tag} : {len(todo)} à générer", flush=True)
    lock = threading.Lock()
    fh = open(out, "a", encoding="utf-8")

    def work(item: dict) -> None:
        body = {"messages": item["prompt"], **PAYLOAD[item["task"]], "seed": 42, "stream": False,
                "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request(f"http://127.0.0.1:{args.port}/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                text = json.loads(resp.read())["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001
            print(f"erreur {item['iid']} : {repr(e)[:120]}", flush=True)
            return
        with lock:
            fh.write(json.dumps({"iid": item["iid"], "model": args.model_tag, "answer": text}, ensure_ascii=False) + "\n")
            fh.flush()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        list(ex.map(work, todo))
    fh.close()


def cmd_judge(args) -> None:
    items = {i["iid"]: i for i in read_jsonl(Path(args.items))}
    gens = [g for p in args.gen for g in read_jsonl(Path(p))]
    rank = {iid: n for n, iid in enumerate(items)}
    gens.sort(key=lambda g: (rank[g["iid"]], g["model"]))  # questions d'abord, puis FR, puis EN
    out = Path(args.out)
    done = {(r["iid"], r["model"]) for r in read_jsonl(out)} if out.exists() else set()
    todo = [g for g in gens if (g["iid"], g["model"]) not in done]
    prices = oc.load_prices(json.load(open(args.models_json))["data"])
    api = oc.OpenRouter(oc.read_key(Path(args.key)), oc.Ledger(Path(args.ledger), args.cap), prices, timeout=args.timeout)
    print(f"{len(todo)} réponses à juger ; compte {api.check_key(GLOBAL_CAP):.4f} $, poste {api.ledger.spent:.4f}/{args.cap} $",
          flush=True)
    params = params_for("off")
    lock = threading.Lock()
    state = {"n": 0, "stopped": False, "by": {}}
    fh = open(out, "a", encoding="utf-8")

    def work(g: dict) -> None:
        if state["stopped"]:
            return
        item = items[g["iid"]]
        user = JUDGE_USER.format(system=item["prompt"][0]["content"], context=judge_context(item["prompt"]),
                                 answer=g["answer"])
        msgs = [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]
        try:
            raw, rec = chat_retry(api, args.model, msgs, 200, params)
        except oc.BudgetExceeded as e:
            state["stopped"] = True
            print(f"ARRÊT plafond : {e}", flush=True)
            return
        except Exception as e:  # noqa: BLE001
            print(f"erreur {g['iid']} : {repr(e)[:120]}", flush=True)
            return
        v = parse_verdict(raw)
        with lock:
            fh.write(json.dumps({"iid": g["iid"], "model": g["model"], "judge": args.model, **v, "cost": rec["cost"]},
                                ensure_ascii=False) + "\n")
            fh.flush()
            state["n"] += 1
            state["by"][v["verdict"]] = state["by"].get(v["verdict"], 0) + 1
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
    print(json.dumps({"judged": state["n"], "verdicts": state["by"], "stopped": state["stopped"],
                      "phase_spent_usd": round(api.ledger.spent, 6)}), flush=True)


def cmd_assemble(args) -> None:
    items = {i["iid"]: i for i in read_jsonl(Path(args.items))}
    answers = {(g["iid"], g["model"]): g["answer"] for p in args.gen for g in read_jsonl(Path(p))}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pairs, counts = [], {}
    for v in read_jsonl(Path(args.verdicts)):
        key = (v["model"], items[v["iid"]]["task"], items[v["iid"]]["lang"])
        c = counts.setdefault("/".join(key), {"judged": 0, "ok": 0, "invention": 0, "manque": 0, "abstention": 0,
                                              "erreur": 0, "pairs": 0})
        c["judged"] += 1
        c[v["verdict"]] += 1
        p = make_pair(items[v["iid"]], v["model"], answers[(v["iid"], v["model"])], v)
        if p is not None:
            pairs.append(p)
            c["pairs"] += 1
    with open(out / "pairs.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps({k: v for k, v in p.items() if k != "sft"}, ensure_ascii=False) + "\n" for p in pairs)
    with open(out / "sft.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(p["sft"], ensure_ascii=False) + "\n" for p in pairs)
    (out / "README.txt").write_text(
        "T9 corrections : réponses fautives de v1.0 et G3b sur des entrées du corpus d'entraînement (final-x4-l5, "
        "qa_train), jugées et corrigées par l'enseignant OpenRouter (t9_corrections.py).\n"
        "pairs.jsonl : prompt, rejected (réponse du modèle), chosen (correction), verdict. "
        "sft.jsonl : lignes d'entraînement corrigées.\n", encoding="utf-8")
    sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(out.glob("*.jsonl"))]
    (out / "SHA256SUMS").write_text("".join(sums))
    print(json.dumps(counts, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("items")
    s.add_argument("--final", required=True)
    s.add_argument("--qa")
    s.add_argument("--out", required=True)
    s = sub.add_parser("gen")
    s.add_argument("--items", required=True)
    s.add_argument("--port", type=int, required=True)
    s.add_argument("--model-tag", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--parallel", type=int, default=4)
    s.add_argument("--limit", type=int, default=0)
    s = sub.add_parser("judge")
    s.add_argument("--items", required=True)
    s.add_argument("--gen", nargs="+", required=True)
    s.add_argument("--model", required=True)
    s.add_argument("--models-json", required=True)
    s.add_argument("--ledger", required=True)
    s.add_argument("--cap", type=float, required=True)
    s.add_argument("--key", default=str(oc.KEY_PATH))
    s.add_argument("--out", required=True)
    s.add_argument("--parallel", type=int, default=8)
    s.add_argument("--timeout", type=float, default=120.0)
    s = sub.add_parser("assemble")
    s.add_argument("--items", required=True)
    s.add_argument("--gen", nargs="+", required=True)
    s.add_argument("--verdicts", required=True)
    s.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "items":
        items = build_items(Path(a.final), Path(a.qa) if a.qa else None)
        with open(a.out, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(i, ensure_ascii=False) + "\n" for i in items)
        n: dict = {}
        for i in items:
            n[f"{i['task']}/{i['lang']}"] = n.get(f"{i['task']}/{i['lang']}", 0) + 1
        print(json.dumps(n))
    else:
        {"gen": cmd_gen, "judge": cmd_judge, "assemble": cmd_assemble}[a.cmd](a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
