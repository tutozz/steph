"""Étiquetage par l'enseignant : construit les messages comme steph, interroge llama-server,
écrit les paires (entrée steph, réponse idéale) pour l'affinage du petit modèle.

Corpus brut (cmd, exit, duration, output) -> messages steph -> enseignant -> étiquette :
    python3 label.py --in corpus.jsonl --out out.jsonl --port 8890 --parallel 4

Cas du banc (messages déjà construits par make_cases.py) -> résultats scorables par score.py :
    python3 label.py --cases cases.json --out results.json --port 8890 --parallel 4

Reprise sur interruption : les identifiants déjà présents dans --out (et dans son
sidecar .rejects.jsonl pour le mode corpus) sont sautés, sans nouvelle requête.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # bench/matrix/score.py
from score import clean  # noqa: E402

from steph.config import Config  # noqa: E402
from steph.digest import digest, extract_facts  # noqa: E402
from steph.prompts import summary_messages  # noqa: E402
from steph.strings import t  # noqa: E402
from steph.textproc import compact_output  # noqa: E402

TRAIN_SYSTEM = (
    "Tu lis la sortie d'une commande de terminal et tu dis à voix haute l'essentiel, en français. "
    "Réponds par une seule ligne courte, 15 mots au plus : d'abord le résultat, puis un détail utile. "
    "Recopie les noms et les nombres exactement comme dans la sortie. Si une information n'est pas "
    "écrite dans la sortie, ne la donne pas : n'invente jamais."
)

TRAIN_SYSTEM_EN = (
    "You read the output of a terminal command and say the essential aloud, in English. "
    "Answer with a single short line, 15 words at most: the result first, then one useful detail. "
    "Copy names and numbers exactly as they appear in the output. If a detail is not "
    "written in the output, do not give it: never invent."
)

TRAIN_SYSTEM_BY_LANG = {"fr": TRAIN_SYSTEM, "en": TRAIN_SYSTEM_EN}


def train_system_for(lang: str) -> str:
    """TRAIN_SYSTEM matching `lang`. `fr` is the untouched, byte-identical default."""
    try:
        return TRAIN_SYSTEM_BY_LANG[lang]
    except KeyError:
        raise ValueError(f"unknown lang: {lang!r} (expected one of {sorted(TRAIN_SYSTEM_BY_LANG)})") from None


MAX_WORDS = 25


def build_messages(rec: dict, max_chars: int, language: str = "fr") -> list[dict]:
    """Messages exacts que steph enverrait pour cet enregistrement (narrator.py : digest, sinon compact,
    bloc de faits L5 quand `facts_block` est actif, comme en production depuis 20cfa0d).

    `language` doit atteindre digest() ET summary_messages() : oublier l'un des deux mélange
    un digest anglais dans un prompt français, ou l'inverse (bogue K2, corrigé ici).
    """
    lines = rec["output"].splitlines()
    out = digest(rec["cmd"], rec["output"], max_chars, language=language) or compact_output(lines, max_chars)
    facts = extract_facts(rec["cmd"], rec["exit"], rec["output"], language) if Config().facts_block else None
    return summary_messages(rec["cmd"], rec["exit"], rec["duration"], out, len(lines), language=language, facts=facts)


def strip_facts_block(user: str, language: str = "fr") -> str:
    """Tour utilisateur sans le bloc de faits L5 : un corpus étiqueté avant L5 et un corpus
    régénéré avec le bloc doivent retrouver le même enregistrement brut."""
    header = "\n" + t(language, "facts.header") + "\n"
    marker = "\nOutput:\n" if language == "en" else "\nSortie :\n"
    start = user.find(header)
    end = user.find(marker, start)
    return user if start < 0 or end < 0 else user[:start] + user[end:]


def query(port: int, messages: list[dict], max_tokens: int, timeout: float, presence_penalty: float = 1.0) -> str:
    """presence_penalty=1.0 : à température 0, le greedy pur part parfois en énumération complète
    d'une liste (ignore la consigne « 3 noms au plus ») ; la pénalité de présence, testée sur
    fx18, corrige ce mode dégénéré sans réintroduire l'aléatoire d'une température non nulle.
    """
    body = json.dumps({
        "messages": messages, "max_tokens": max_tokens, "temperature": 0, "top_p": 0.9,
        "presence_penalty": presence_penalty,
        "stream": False, "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", body,
                                  {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def judge(raw: str) -> tuple[str | None, str]:
    """Nettoie et applique les rejets. Le contrôle « <think> » porte sur le texte BRUT, avant
    nettoyage : un <think> ouvert sans fermeture laisse fuir du raisonnement que `clean()` ne
    retire pas (sa première regex exige les deux balises), donc le vérifier après serait trop tard.
    """
    if "<think>" in raw:
        return None, "think"
    text = clean(raw)
    if not text.strip():
        return None, "vide"
    if len(text.split()) > MAX_WORDS:
        return None, "trop long"
    return text, "ok"


class Writer:
    """Écriture jsonl append, verrouillée, un flush par ligne (reprise possible à tout instant)."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.f = open(path, "a", encoding="utf-8")

    def write(self, row: dict) -> None:
        with self.lock:
            self.f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.f.flush()

    def close(self) -> None:
        self.f.close()


def done_ids(out: Path, rejects: Path) -> set[str]:
    ids: set[str] = set()
    for p in (out, rejects):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    ids.add(json.loads(line)["id"])
    return ids


def run_corpus(args) -> None:
    records = [json.loads(l) for l in open(args.infile, encoding="utf-8") if l.strip()]
    for i, r in enumerate(records):
        r["id"] = f"{r.get('machine', 'x')}:{i}"

    out = Path(args.out)
    rejects = out.with_suffix(".rejects.jsonl")
    seen = done_ids(out, rejects)
    todo = [r for r in records if r["id"] not in seen]
    print(f"{len(records)} enregistrements, {len(seen)} déjà faits, {len(todo)} à faire", flush=True)
    if not todo:
        return

    writer, rej_writer = Writer(out), Writer(rejects)
    counts = {"ok": 0, "think": 0, "vide": 0, "trop long": 0, "erreur": 0}
    lock = threading.Lock()
    train_system = train_system_for(args.lang)

    def work(rec: dict) -> None:
        try:
            msgs = build_messages(rec, args.max_chars, args.lang)
            raw = query(args.port, msgs, args.max_tokens, args.timeout, args.presence_penalty)
            label, reason = judge(raw)
        except Exception as e:
            with lock:
                counts["erreur"] += 1
            rej_writer.write({"id": rec["id"], "reason": f"erreur: {e!r}"})
            return
        with lock:
            counts[reason] += 1
        if label is None:
            rej_writer.write({"id": rec["id"], "reason": reason, "raw": raw[:300]})
            return
        train_msgs = [{"role": "system", "content": train_system},
                      {"role": "user", "content": msgs[1]["content"]},
                      {"role": "assistant", "content": label}]
        writer.write({**rec, "input_messages": msgs, "label": label, "train_messages": train_msgs})

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        list(ex.map(work, todo))
    elapsed = time.time() - t0
    writer.close()
    rej_writer.close()
    rate = len(todo) / elapsed * 60 if elapsed else 0.0
    print(json.dumps({"traites": len(todo), "elapsed_s": round(elapsed, 1),
                      "par_min": round(rate, 1), **counts}, ensure_ascii=False))


def run_cases(args) -> None:
    cases = json.load(open(args.cases, encoding="utf-8"))
    out = Path(args.out)
    done = set()
    rows = []
    if out.exists():
        prev = json.load(open(out, encoding="utf-8"))
        rows = prev.get("rows", [])
        done = {r["id"] for r in rows}
    todo = [c for c in cases if c["id"] not in done]
    print(f"{len(cases)} cas, {len(done)} déjà faits, {len(todo)} à faire", flush=True)
    lock = threading.Lock()

    def work(c: dict) -> dict:
        max_tokens = 120 if c["kind"] == "qa" else 90
        try:
            out_text = query(args.port, c["messages"], max_tokens, args.timeout, args.presence_penalty)
        except Exception as e:
            return {"id": c["id"], "fixture": c["fixture"], "kind": c["kind"], "out": None, "error": str(e)[:200]}
        return {"id": c["id"], "fixture": c["fixture"], "kind": c["kind"], "out": out_text}

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        for row in ex.map(work, todo):
            with lock:
                rows.append(row)
                json.dump({"label": "qwen3.5-9b-teacher", "rows": rows}, open(out, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
    elapsed = time.time() - t0
    print(json.dumps({"traites": len(todo), "elapsed_s": round(elapsed, 1)}, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--in", dest="infile", help="corpus jsonl brut (cmd, exit, duration, output)")
    g.add_argument("--cases", help="cases.json du banc (messages déjà construits)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=8890)
    ap.add_argument("--parallel", type=int, default=4, help="requêtes concurrentes (= slots du serveur)")
    ap.add_argument("--max-chars", type=int, default=1500, help="budget digest/compact, comme cfg.summary_chars")
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--presence-penalty", type=float, default=1.0,
                    help="voir query() : corrige l'énumération complète en mode greedy pur")
    ap.add_argument("--lang", default="fr", choices=sorted(TRAIN_SYSTEM_BY_LANG),
                    help="langue de TRAIN_SYSTEM dans train_messages (mode --in seulement)")
    args = ap.parse_args()

    # chauffe : cache du prompt système, hors mesure de débit
    query(args.port, summary_messages("true", 0, 0.0, "", 0), 4, args.timeout, args.presence_penalty)

    if args.cases:
        run_cases(args)
    else:
        run_corpus(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
