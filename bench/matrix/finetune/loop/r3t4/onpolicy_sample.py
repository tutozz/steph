"""R3-T4 partie 1 : sorties on-policy de R1 sur des entrées de data/final-x4, sur la machine du corpus.

    python3 onpolicy_sample.py prints --bench-cases CASES_DIR --speak-bench DATA_V1 --out prints.json   # Mac
    python3 onpolicy_sample.py select --final DIR --final-extra DIR --prints prints.json \\
        --total 1500 --en-cap 500 --seed 3 --out selected.jsonl
    python3 onpolicy_sample.py sample --selected selected.jsonl --ports 8990,8991,8992,8993 --n 6 --out samples.jsonl
    python3 onpolicy_sample.py stats --selected selected.jsonl --samples samples.jsonl [--first 4]

- prints : empreintes (lignes normalisées et 5-grammes, v3-fp1 de leak_check.py) des 1 083 cas du banc v3
  et de Steph Speak Bench v1 ; aucun texte, seulement des hachages.
- select : résumés FR et EN de final-x4 (et summary_residual, questions qa_train de data/final, que R2
  reprend), tour utilisateur reconstruit au format de production du profil affiné (narrator.py : digest
  à 587 caractères, prompt SUMMARY_SYSTEM_FINETUNED), gardés si le modèle est atteint en production (reaches : v3lib.reaches_model avec le vrai nombre de lignes) et si aucune
  empreinte ne touche un cas des bancs (mêmes seuils que leak_check.py) ; tirage stratifié par fichier,
  anglais plafonné.
- sample : n sorties par entrée, paramètres du résumé en production (température 0,2, top_p 0,9,
  90 jetons ; questions 0,3, 400 jetons), graine = indice de la sortie + 1, reprise possible.
Les fichiers écrits contiennent du texte de corpus et restent sur la machine ; seuls des comptes sont imprimés.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "bench" / "matrix" / "finetune"))
sys.path.insert(0, str(REPO / "bench" / "matrix" / "v3" / "tools"))

from leak_check import CMD_LINE, fp, jac, norm_cmd  # noqa: E402
from steph import prompts  # noqa: E402
from steph.digest import digest  # noqa: E402
from steph.textproc import compact_output  # noqa: E402

FINETUNED_SUMMARY_CHARS = 587  # narrator.FINETUNED_SUMMARY_CHARS
VERBATIM_MAX_WORDS = 20  # config.read_verbatim_max_words
# LLM.stream, Narrator._llm_say, ControlServer._ask (mêmes valeurs que v3lib.PRODUCTION_PAYLOAD, X5)
PAYLOAD = {"summary": {"temperature": 0.2, "top_p": 0.9, "max_tokens": 90},
           "qa": {"temperature": 0.3, "top_p": 0.9, "max_tokens": 400}}
SUMMARY_FILES = ["macos", "linux-low", "linux-dev", "snapshot-linux-dev", "snapshot-linux-low",
                 "macos.en", "linux-low.en"]

_TURN = {
    "fr": re.compile(r"^Commande : (?P<cmd>.*?)\nStatut : (?P<status>[^\n]*)\n"
                     r"Durée : (?P<dur>[\d.]+) s ; (?P<n>\d+) lignes affichées\n"
                     r"(?:Faits extraits en code :\n(?P<facts>(?:- [^\n]*\n)+))?Sortie :\n(?P<out>.*)\Z", re.S),
    "en": re.compile(r"^Command: (?P<cmd>.*?)\nStatus: (?P<status>[^\n]*)\n"
                     r"Duration: (?P<dur>[\d.]+) s; (?P<n>\d+) lines displayed\n"
                     r"(?:Facts extracted by code:\n(?P<facts>(?:- [^\n]*\n)+))?Output:\n(?P<out>.*)\Z", re.S),
}
_PLACEHOLDER = {"fr": "(aucune sortie)", "en": "(no output)"}
_CODE = re.compile(r"code (\d+)\)")


def lang_of(name: str) -> str:
    return "en" if name.endswith(".en") else "fr"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def parse_user(user: str, lang: str) -> dict | None:
    m = _TURN[lang].match(user)
    if not m:
        return None
    code = _CODE.search(m["status"])
    out = m["out"]
    return {"cmd": m["cmd"], "exit": int(code[1]) if code else None, "duration": float(m["dur"]),
            "nlines": int(m["n"]), "output": "" if out.strip() == _PLACEHOLDER[lang] else out,
            "facts": [f[2:] for f in m["facts"].splitlines()] if m["facts"] else None}


def payload(task: str) -> dict:
    return dict(PAYLOAD[task])


def reaches(rec: dict, lang: str) -> bool:
    """v3lib.reaches_model, avec le vrai nombre de lignes de l'en-tête : la sortie étiquetée est
    parfois déjà un digest de quelques lignes, que la règle « dit tel quel » prendrait à tort."""
    from steph.digest import resolve
    text = rec["output"].strip()
    if not text:
        return False
    if rec["exit"] == 127 and re.search(r"not found|introuvable|non trouvée", text):
        return False
    if len(text.split()) <= VERBATIM_MAX_WORDS and max(rec["nlines"], len(text.split("\n"))) <= 3:
        return False
    return not resolve(rec["cmd"], rec["exit"], text, lang)


def production_messages(rec: dict, lang: str) -> list[dict]:
    """narrator._summarize, profil affiné, appliqué à la sortie telle qu'étiquetée.

    Le bloc de faits (L5) vient de la ligne elle-même : extrait de la sortie brute par
    x4_l5_inputs.py, il ne se recalcule pas sur une sortie déjà réduite. Une ligne d'avant L5 n'en a pas."""
    out = (digest(rec["cmd"], rec["output"], FINETUNED_SUMMARY_CHARS, lang)
           or compact_output(rec["output"].splitlines(), FINETUNED_SUMMARY_CHARS))
    return prompts.finetuned_summary_messages(rec["cmd"], rec["exit"], rec["duration"], out, rec["nlines"],
                                              language=lang, facts=rec.get("facts"))


# ---------------------------------------------------------------- contamination (seuils de leak_check.py)
def rep(text: str) -> dict:
    lines, shingles = fp(text)
    return {"lines": sorted(lines), "shingles": sorted(shingles)}


class BenchIndex:
    def __init__(self, cases: list[dict]):
        self.reps: list[tuple[set, set, set]] = []
        self.by_line: dict[str, set[int]] = collections.defaultdict(set)
        for case in cases:
            for r in case["reps"]:
                k = len(self.reps)
                self.reps.append((set(r["lines"]), set(r["shingles"]), set(case["cmds"])))
                for h in r["lines"]:
                    self.by_line[h].add(k)

    def hit(self, texts: list[str], cmds: list[str]) -> bool:
        own_cmds = {norm_cmd(c) for c in cmds} | {norm_cmd(c) for t in texts for c in CMD_LINE.findall(t)}
        for text in texts:
            lines, shingles = fp(text)
            for k in set().union(*(self.by_line.get(h, set()) for h in lines)) if lines else ():
                c_lines, c_sh, c_cmds = self.reps[k]
                j = jac(lines, c_lines)
                if j >= 0.5 or jac(shingles, c_sh) >= 0.6 or (j >= 0.3 and own_cmds & c_cmds):
                    return True
        return False


def bench_prints(cases_dir: Path, speak_dir: Path) -> list[dict]:
    from leak_check import case_prints
    out = [case_prints(json.loads(line)) for p in sorted(cases_dir.rglob("*.jsonl"))
           for line in p.open(encoding="utf-8") if line.strip()]
    for p in sorted(speak_dir.glob("*/*.jsonl")):
        for line in p.open(encoding="utf-8"):
            if not line.strip():
                continue
            c = json.loads(line)
            outs = [h["output"] for h in c["history"]] if c.get("task") == "qa" else [c.get("output", "")]
            cmds = [h["cmd"] for h in c["history"]] if c.get("task") == "qa" else [c.get("cmd", "")]
            out.append({"id": f"speak-{c['lang']}-{c['id']}", "cmds": [norm_cmd(x) for x in cmds if x],
                        "reps": [rep("\n".join(outs))]})
    return out


# ---------------------------------------------------------------- tirage
def allocate(eligible: dict[str, int], total: int, en_cap: int) -> dict[str, int]:
    """Anglais : tout jusqu'à en_cap ; français : le reste, au prorata de chaque fichier."""
    def share(names: list[str], budget: int) -> dict[str, int]:
        pool = sum(eligible[n] for n in names)
        if pool <= budget:
            return {n: eligible[n] for n in names}
        exact = {n: budget * eligible[n] / pool for n in names}
        alloc = {n: int(v) for n, v in exact.items()}
        for n in sorted(names, key=lambda n: exact[n] - alloc[n], reverse=True)[:budget - sum(alloc.values())]:
            alloc[n] += 1
        return alloc

    en = share([n for n in eligible if lang_of(n) == "en"], en_cap)
    fr = share([n for n in eligible if lang_of(n) == "fr"], total - sum(en.values()))
    return {**fr, **en}


def select(args) -> None:
    from compose_k3 import strip_status
    index = BenchIndex(json.load(open(args.prints)))
    counts: collections.Counter = collections.Counter()
    eligible: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for name in SUMMARY_FILES + ["summary_residual"]:
        lang = lang_of(name)
        rows = []
        folder = args.final_extra if name == "summary_residual" else args.final
        for line in (folder / f"{name}.jsonl").open(encoding="utf-8"):
            if not line.strip():
                continue
            row = json.loads(line)
            counts[f"{name}:rows"] += 1
            user = next(m["content"] for m in row["messages"] if m["role"] == "user")
            label = row["messages"][-1]["content"]
            rec = parse_user(user, lang)
            if rec is None:
                counts[f"{name}:unparsed"] += 1
                continue
            if not reaches(rec, lang):
                counts[f"{name}:no_model"] += 1
                continue
            msgs = production_messages(rec, lang)
            if index.hit([user, msgs[1]["content"]], [rec["cmd"]]):
                counts[f"{name}:bench_overlap"] += 1
                continue
            key = sha(msgs[0]["content"] + "\x00" + msgs[1]["content"])
            if key in seen:
                counts[f"{name}:duplicate"] += 1
                continue
            seen.add(key)
            counts[f"{name}:redigested"] += msgs[1]["content"] != user
            rows.append({"id": key[:16], "task": "summary", "source": name, "lang": lang, "entry_sha": sha(user),
                         "messages": msgs, "label": strip_status(label, lang), "label_raw": label})
        eligible[name] = rows
    qa = []
    for line in (args.final_extra / "qa_train.jsonl").open(encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        counts["qa_train:rows"] += 1
        msgs = row["messages"][:-1]
        users = [m["content"] for m in msgs if m["role"] == "user"]
        if index.hit(users, []):
            counts["qa_train:bench_overlap"] += 1
            continue
        key = sha("\x00".join(m["content"] for m in msgs))
        if key in seen:
            counts["qa_train:duplicate"] += 1
            continue
        seen.add(key)
        label = row["messages"][-1]["content"]
        qa.append({"id": key[:16], "task": "qa", "source": "qa_train", "lang": "fr", "entry_sha": sha(users[-1]),
                   "messages": msgs, "label": label, "label_raw": label})
    eligible["qa_train"] = qa
    alloc = allocate({n: len(r) for n, r in eligible.items()}, args.total, args.en_cap)
    rng = random.Random(args.seed)
    chosen = [r for n in eligible for r in rng.sample(eligible[n], alloc[n])]
    with args.out.open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in chosen)
    report = {"counts": dict(sorted(counts.items())), "eligible": {n: len(r) for n, r in eligible.items()},
              "allocated": alloc, "selected": len(chosen),
              "by_lang": dict(collections.Counter(r["lang"] for r in chosen)),
              "selected_sha256": sha("".join(r["id"] for r in chosen))}
    print(json.dumps(report, ensure_ascii=False))


# ---------------------------------------------------------------- échantillonnage
def complete(port: int, messages: list[dict], task: str, seed: int, timeout: float) -> dict:
    body = json.dumps({"messages": messages, **PAYLOAD[task], "seed": seed, "stream": False, "cache_prompt": True,
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", body,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    choice = data["choices"][0]
    return {"text": choice["message"]["content"].strip(), "finish": choice.get("finish_reason"),
            "tokens": data.get("usage", {}).get("completion_tokens")}


def sample(args) -> None:
    ports = [int(p) for p in args.ports.split(",")]
    rows = [json.loads(line) for line in args.selected.open(encoding="utf-8") if line.strip()]
    done = set()
    if args.out.exists():
        done = {(d["id"], d["k"]) for d in map(json.loads, args.out.open(encoding="utf-8")) if d.get("text") is not None}
    # toutes les sorties d'une entrée à la suite, sur le même serveur : le préfixe en cache sert k fois
    jobs = [(r, [k for k in range(args.n) if (r["id"], k) not in done]) for r in rows]
    jobs = [j for j in jobs if j[1]]
    todo = sum(len(ks) for _, ks in jobs)
    lock, counter = threading.Lock(), collections.Counter()
    t0 = time.time()

    def work(i_job):
        i, (r, ks) = i_job
        port = ports[i % len(ports)]
        for k in ks:
            for attempt in range(3):
                try:
                    res = complete(port, r["messages"], r["task"], seed=k + 1, timeout=args.timeout)
                    break
                except Exception as e:  # noqa: BLE001 - reprise simple, erreur comptée
                    res = {"text": None, "error": type(e).__name__}
                    time.sleep(2 * (attempt + 1))
            with lock:
                with args.out.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"id": r["id"], "task": r["task"], "lang": r["lang"], "k": k, "seed": k + 1,
                                        **res}, ensure_ascii=False) + "\n")
                counter["ok" if res.get("text") is not None else "error"] += 1
                n = sum(counter.values())
                if n % 200 == 0:
                    print(json.dumps({"done": n, "todo": todo, **counter, "s": round(time.time() - t0)}), flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(work, enumerate(jobs)))
    print(json.dumps({"done": sum(counter.values()), "skipped_already_done": len(done), **counter,
                      "s": round(time.time() - t0)}), flush=True)


def stats(selected: list[dict], samples: list[dict]) -> dict:
    """Comptes seulement : sorties distinctes par entrée, longueurs contre l'étiquette, charge du juge."""
    by_id = {r["id"]: r for r in selected}
    groups: dict[str, dict] = collections.defaultdict(lambda: {"entries": set(), "samples": 0, "errors": 0,
                                                               "truncated": 0, "empty": 0, "words": [],
                                                               "texts": collections.defaultdict(set)})
    for d in samples:
        r = by_id[d["id"]]
        for key in (f"{r['task']}/{r['lang']}", "all"):
            g = groups[key]
            g["entries"].add(d["id"])
            if d.get("text") is None:
                g["errors"] += 1
                continue
            g["samples"] += 1
            g["truncated"] += d.get("finish") == "length"
            g["empty"] += not d["text"].strip()
            g["words"].append(len(d["text"].split()))
            g["texts"][d["id"]].add(d["text"])
    out = {}
    for key, g in sorted(groups.items()):
        labels = [len(by_id[i]["label"].split()) for i in g["entries"]]
        out[key] = {"entries": len(g["entries"]), "samples": g["samples"], "errors": g["errors"],
                    "truncated": g["truncated"], "empty": g["empty"],
                    "distinct_per_entry": dict(sorted(collections.Counter(str(len(v)) for v in g["texts"].values()).items())),
                    "unique_to_judge": sum(len(v) for v in g["texts"].values()),
                    "words_mean": round(sum(g["words"]) / len(g["words"]), 2) if g["words"] else 0,
                    "label_words_mean": round(sum(labels) / len(labels), 2) if labels else 0}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prints")
    p.add_argument("--bench-cases", type=Path, required=True)
    p.add_argument("--speak-bench", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("select")
    p.add_argument("--final", type=Path, required=True)
    p.add_argument("--final-extra", type=Path, required=True, help="data/final : qa_train, summary_residual")
    p.add_argument("--prints", type=Path, required=True)
    p.add_argument("--total", type=int, default=1500)
    p.add_argument("--en-cap", type=int, default=500)
    p.add_argument("--seed", type=int, default=3)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("sample")
    p.add_argument("--selected", type=Path, required=True)
    p.add_argument("--ports", required=True)
    p.add_argument("--n", type=int, default=4)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("stats")
    p.add_argument("--selected", type=Path, required=True)
    p.add_argument("--samples", type=Path, required=True)
    p.add_argument("--first", type=int, default=0, help="seulement les sorties k < first (0 : toutes)")
    args = ap.parse_args()
    if args.cmd == "stats":
        read = lambda p: [json.loads(line) for line in p.open(encoding="utf-8") if line.strip()]  # noqa: E731
        samples = [d for d in read(args.samples) if not args.first or d["k"] < args.first]
        print(json.dumps(stats(read(args.selected), samples), ensure_ascii=False))
        return
    if args.cmd == "prints":
        prints = bench_prints(args.bench_cases, args.speak_bench)
        args.out.write_text(json.dumps(prints))
        print(json.dumps({"prints": len(prints)}))
    else:
        {"select": select, "sample": sample}[args.cmd](args)


if __name__ == "__main__":
    main()
