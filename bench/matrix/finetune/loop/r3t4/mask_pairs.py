"""R3-T4 partie 2 : juge A7 des sorties on-policy de R1, empans inventés, paires Mask-DPO.

    PYTHONPATH=<judge_lib A7>:<ce dossier> JUDGE_PORT=8977 python3 mask_pairs.py judge --pass A \
        --selected selected.jsonl --samples samples.jsonl --cache cache/ --shard 0 --nshards 1
    python3 mask_pairs.py judge --pass B ...     # seulement les entrées où la passe A voit une invention
    python3 mask_pairs.py build --selected selected.jsonl --samples samples.jsonl --cache cache/ --out pairs/

- judge : juge A7 intact (judge_lib.call_judge), une réponse par texte distinct et par entrée
  (cache par empreinte entrée + réponse, octet pour octet) ; la liste est découpée en parts
  disjointes, une part par serveur juge, fusionnées à la lecture du cache.
- verdict final comme judge_v3.py : invention si les deux passes le disent, douteux si une seule.
- build : rejetée = sortie à invention dont l'empan est retrouvé dans le texte ; choisie = sortie
  fidèle (ok aux deux passes) la plus proche en caractères de l'étiquette 27B ; au plus
  max_pairs rejetées distinctes par entrée ; val = entrées dont l'empreinte tombe sous val_frac.
Les fichiers écrits contiennent du texte de corpus et restent sur la machine ; seuls des comptes
sont imprimés.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ---------------------------------------------------------------- empans
_TRIM = " \t\n\"'«»“”‘’`.,;:!?()[]"
_ANCHOR = re.compile(r"\d+(?:[.,:]\d+)*|[\w-]*[./_-][\w./_-]*\w|[A-Za-z]+\d[\w]*")
_WORD = re.compile(r"[\w'’-]+")
_STATUS = {
    "fail": re.compile(r"\b(échec|échoué\w*|échoue\w*|fail\w*|erreur\w*|error\w*)\b", re.I),
    "ok": re.compile(r"\b(succès|réussi\w*|success\w*|succeed\w*|ok)\b", re.I),
}


def _find_all(text: str, needle: str) -> list[tuple[int, int]]:
    if not needle:
        return []
    pat = re.compile(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", re.I)
    return [(mt.start(), mt.end()) for mt in pat.finditer(text)]


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [tuple(x) for x in out]


def _fact_spans(text: str, fact: str) -> list[tuple[int, int]]:
    fact = fact.strip(_TRIM)
    exact = _find_all(text, fact)
    if exact:
        return exact
    spans = [sp for a in _ANCHOR.findall(fact) for sp in _find_all(text, a)]
    for family, pat in _STATUS.items():
        if pat.search(fact):
            spans += [(mt.start(), mt.end()) for mt in pat.finditer(text)]
    if spans:
        return spans
    words = _WORD.findall(fact)
    for n in range(len(words), 1, -1):
        for i in range(len(words) - n + 1):
            seq = words[i:i + n]
            if max(len(w) for w in seq) < 4:
                continue
            pat = re.compile(r"(?<!\w)" + r"\W+".join(re.escape(w) for w in seq) + r"(?!\w)", re.I)
            found = [(mt.start(), mt.end()) for mt in pat.finditer(text)]
            if found:
                return found
    return []


def locate_spans(text: str, inventions: list[str]) -> list[tuple[int, int]]:
    """Empans (caractères) de la réponse qui portent les faits inventés listés par le juge."""
    return _merge([sp for f in inventions if isinstance(f, str) for sp in _fact_spans(text, f)])


def token_keep(offsets: list[tuple[int, int]], spans: list[tuple[int, int]], shift: int) -> list[bool]:
    """Jetons dont l'intervalle (décalé de `shift`, début de la réponse) touche un empan."""
    keep = []
    for s, e in offsets:
        s, e = s - shift, e - shift
        keep.append(e > s and any(s < se and e > ss for ss, se in spans))
    return keep


# ---------------------------------------------------------------- juge
def cache_key(entry_id: str, text: str) -> str:
    return hashlib.sha256(f"{entry_id}\x00{text}".encode()).hexdigest()


def final_verdict(va: str, vb: str) -> str:
    if va == vb == "invention":
        return "invention"
    if "invention" in (va, vb):
        return "douteux"
    return "erreur" if "erreur" in (va, vb) else "ok"


def needs_pass_b(unique: set[tuple[str, str]], pass_a: dict[str, str]) -> set[tuple[str, str]]:
    hot = {eid for eid, t in unique if pass_a.get(cache_key(eid, t)) == "invention"}
    return {(eid, t) for eid, t in unique if eid in hot}


def shard(keys: list[str], i: int, n: int) -> list[str]:
    return [k for k in keys if int(hashlib.sha256(k.encode()).hexdigest()[:8], 16) % n == i]


def judge_context(messages: list[dict]) -> str:
    """judge_v3.judge_context : tous les messages utilisateur, historique puis question."""
    return "\n\n".join(x["content"] for x in messages if x["role"] == "user")


def load_cache(folder: Path, pass_id: str) -> dict[str, dict]:
    out = {}
    for p in sorted(glob.glob(str(folder / f"pass{pass_id}-*.jsonl"))):
        for line in open(p, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                if r["verdict"] in ("ok", "invention"):
                    out[r["key"]] = r
    return out


def call_retry(ctx: str, phrase: str, pass_id: str) -> dict:
    from judge_lib import call_judge
    last = {"verdict": "erreur", "inventions": []}
    for _ in range(3):
        try:
            r = call_judge(ctx, phrase, pass_id=pass_id, timeout=900)
        except Exception as e:  # noqa: BLE001 - HTTP 400 ou délai : compté comme erreur
            r = {"verdict": "erreur", "inventions": [], "_error": str(e)[:200]}
        if r["verdict"] in ("ok", "invention"):
            return r
        last = r
        time.sleep(1)
    return last


def load_rows(selected: Path, samples: Path):
    entries = {r["id"]: r for r in map(json.loads, open(selected, encoding="utf-8"))}
    outs = collections.defaultdict(list)
    for s in map(json.loads, open(samples, encoding="utf-8")):
        if s.get("text") is not None:
            outs[s["id"]].append(s)
    for v in outs.values():
        v.sort(key=lambda s: s["k"])
        seen, uniq = set(), []
        for s in v:  # une reprise peut réécrire une sortie : on garde la première par k
            if s["k"] not in seen:
                seen.add(s["k"]); uniq.append(s)
        v[:] = uniq
    return entries, outs


def judge(args) -> None:
    entries, outs = load_rows(args.selected, args.samples)
    unique = {(eid, s["text"]) for eid, v in outs.items() for s in v if s["text"].strip()}
    if args.pass_id == "B":
        pass_a = {k: r["verdict"] for k, r in load_cache(args.cache, "A").items()}
        missing = [u for u in unique if cache_key(*u) not in pass_a]
        if len(missing) > args.max_missing:
            raise SystemExit(f"passe A incomplète : {len(missing)} réponses sans verdict")
        if missing:  # verdict illisible trois fois : la réponse reste sans verdict, donc hors paires
            print(json.dumps({"pass_a_missing": len(missing)}), flush=True)
        unique = needs_pass_b(unique, pass_a)
    done = load_cache(args.cache, args.pass_id)
    by_key = {cache_key(*u): u for u in unique}
    todo = [k for k in shard(sorted(by_key), args.shard, args.nshards) if k not in done]
    args.cache.mkdir(parents=True, exist_ok=True)
    out = args.cache / f"pass{args.pass_id}-{args.shard}.jsonl"
    counter, t0 = collections.Counter(), time.time()

    def work(k):
        eid, text = by_key[k]
        return k, call_retry(judge_context(entries[eid]["messages"]), text, args.pass_id)

    with ThreadPoolExecutor(args.threads) as pool, out.open("a", encoding="utf-8") as f:
        for i, (k, r) in enumerate(pool.map(work, todo), 1):
            f.write(json.dumps({"key": k, "verdict": r["verdict"], "inventions": r.get("inventions", [])},
                               ensure_ascii=False) + "\n")
            f.flush()
            counter[r["verdict"]] += 1
            if i % 100 == 0 or i == len(todo):
                print(json.dumps({"pass": args.pass_id, "shard": args.shard, "done": i, "todo": len(todo),
                                  **counter, "s": round(time.time() - t0)}), flush=True)
    print(json.dumps({"pass": args.pass_id, "unique": len(unique), "shard_todo": len(todo),
                      "already": len(done), **counter}), flush=True)


# ---------------------------------------------------------------- paires
def entry_pairs(entry: dict, outs: list[dict], verdicts: dict[str, dict], max_pairs: int):
    """Paires d'une entrée et la raison quand il n'y en a pas."""
    finals = [(s["text"], verdicts.get(cache_key(entry["id"], s["text"]))) for s in outs if s["text"].strip()]
    inventive = [(t, v) for t, v in finals if v and v["final"] == "invention"]
    if not inventive:
        return [], "no_invention"
    faithful = [t for t, v in finals if v and v["final"] == "ok"]
    if not faithful:
        return [], "no_faithful"
    chosen = min(faithful, key=lambda t: abs(len(t) - len(entry["label"])))
    pairs, seen = [], set()
    for t, v in inventive:
        if t in seen:
            continue
        seen.add(t)
        spans = locate_spans(t, v["inventions"])
        if spans and len(pairs) < max_pairs:
            pairs.append({"id": entry["id"], "task": entry["task"], "lang": entry["lang"],
                          "prompt": entry["messages"], "chosen": chosen, "rejected": t,
                          "rejected_spans": [list(s) for s in spans], "inventions": v["inventions"]})
    return pairs, ("pairs" if pairs else "no_span")


def length_ratio(pairs: list[dict]) -> float:
    """Longueur moyenne (mots) des rejetées sur celle des choisies."""
    rej = sum(len(p["rejected"].split()) for p in pairs) / len(pairs)
    cho = sum(len(p["chosen"].split()) for p in pairs) / len(pairs)
    return rej / cho


def length_filter(pairs: list[dict], max_ratio: float) -> list[dict]:
    """Écarte les paires dont la rejetée dépasse max_ratio fois la choisie en mots (effet R2-C1)."""
    return [p for p in pairs if len(p["rejected"].split()) <= max_ratio * max(1, len(p["chosen"].split()))]


def build(args) -> None:
    entries, outs = load_rows(args.selected, args.samples)
    va, vb = load_cache(args.cache, "A"), load_cache(args.cache, "B")
    verdicts = {}
    for k, a in va.items():
        b = vb.get(k)
        if b is None:
            verdicts[k] = {"final": "ok" if a["verdict"] == "ok" else "douteux", "inventions": a["inventions"],
                           "pass_b": False}
        else:
            verdicts[k] = {"final": final_verdict(a["verdict"], b["verdict"]),
                           "inventions": a["inventions"] + [x for x in b["inventions"] if x not in a["inventions"]],
                           "pass_b": True}
    why, pairs = collections.Counter(), []
    finals = collections.Counter()
    for eid, v in outs.items():
        for s in v:
            if s["text"].strip():
                finals[(verdicts.get(cache_key(eid, s["text"])) or {"final": "non_juge"})["final"]] += 1
        p, reason = entry_pairs(entries[eid], v, verdicts, args.max_pairs)
        why[reason] += 1
        pairs += p
    before = len(pairs)
    if args.max_pair_ratio:
        pairs = length_filter(pairs, args.max_pair_ratio)
    args.out.mkdir(parents=True, exist_ok=True)
    is_val = lambda p: int(hashlib.sha256(p["id"].encode()).hexdigest()[:8], 16) / 16**8 < args.val_frac  # noqa: E731
    train = [p for p in pairs if not is_val(p)]
    val = [p for p in pairs if is_val(p)]
    for name, rows in (("pairs-train.jsonl", train), ("pairs-val.jsonl", val)):
        with (args.out / name).open("w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    words = lambda key: round(sum(len(p[key].split()) for p in pairs) / max(1, len(pairs)), 2)  # noqa: E731
    span_share = [sum(e - s for s, e in p["rejected_spans"]) / max(1, len(p["rejected"])) for p in pairs]
    report = {"entries": len(entries), "entries_sampled": len(outs),
              "outputs_by_final": dict(finals), "entries_by_reason": dict(why),
              "pairs_before_length_filter": before, "pairs": len(pairs), "train": len(train), "val": len(val),
              "by_lang": dict(collections.Counter(p["lang"] for p in pairs)),
              "by_task": dict(collections.Counter(p["task"] for p in pairs)),
              "chars_ratio_rejected_over_chosen": round(sum(len(p["rejected"]) for p in pairs)
                                                        / max(1, sum(len(p["chosen"]) for p in pairs)), 3),
              "words_chosen": words("chosen"), "words_rejected": words("rejected"),
              "length_ratio_rejected_over_chosen": round(length_ratio(pairs), 3) if pairs else None,
              "span_share_of_rejected_chars": round(sum(span_share) / max(1, len(span_share)), 3)}
    (args.out / "pairs-counts.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("judge", "build"):
        p = sub.add_parser(name)
        p.add_argument("--selected", type=Path, required=True)
        p.add_argument("--samples", type=Path, required=True)
        p.add_argument("--cache", type=Path, required=True)
    p = sub.choices["judge"]
    p.add_argument("--pass", dest="pass_id", choices=["A", "B"], required=True)
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--nshards", type=int, default=1)
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--max-missing", type=int, default=0, help="passe B : réponses sans verdict A tolérées")
    p = sub.choices["build"]
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-pairs", type=int, default=2)
    p.add_argument("--val-frac", type=float, default=0.08)
    p.add_argument("--max-pair-ratio", type=float, default=0.0, help="mots rejetée / choisie, 0 : pas de filtre")
    args = ap.parse_args()
    {"judge": judge, "build": build}[args.cmd](args)


if __name__ == "__main__":
    main()
