#!/usr/bin/env python3
"""R2-C1: DPO pairs whose rejected answer is the grounded label with one rule-injected invention
(TrueBrief, arXiv 2601.04212): intrinsic (a number, an exit code, a status or a file name of the
label altered against the context) or extrinsic (a plausible fact absent from the context).

    python3 inject_pairs.py --data <mix dir> --out <dir> --train 800 --val 60 --fr-share 0.667 --seed 20260928

chosen = label, rejected = label with one invention; one pair per prompt; prompts deduplicated;
FR prompts weighted to --fr-share. Writes pairs-train.jsonl and pairs-val.jsonl (corpus text:
they stay on the corpus host) and inject-counts.json (counts only).

SPDX-License-Identifier: MIT
"""

import argparse
import collections
import json
import random
import re
from pathlib import Path

NUM = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(?![\w])")
FILE = re.compile(r"(?<![\w/.-])([\w-]+)\.(py|js|ts|tsx|json|ya?ml|toml|txt|md|c|h|cpp|rs|go|sh|log|conf|cfg|lock|csv|"
                  r"html|css|java|rb|php|sql|ini|xml)\b")
ADDRESS = re.compile(r"\d+\.\d+\.\d+\.\d+|[0-9a-f]*:[0-9a-f]*:", re.I)
CODE = re.compile(r"(code(?: de sortie)?|exit code|exit status)\s*(\d+)", re.I)
STATUS = {
    "fr": [("réussi", "échoué"), ("Réussi", "Échoué"), ("échoué", "réussi"), ("Échoué", "Réussi"), ("Échec", "Succès"),
           ("échec", "succès"), ("Succès", "Échec"), ("succès", "échec"), ("terminé", "interrompu"), ("Terminé", "Interrompu")],
    "en": [("succeeded", "failed"), ("Succeeded", "Failed"), ("failed", "succeeded"), ("Failed", "Succeeded"),
           ("success", "failure"), ("Success", "Failure"), ("passed", "failed"), ("Passed", "Failed"), ("done", "aborted"),
           ("Done", "Aborted")],
}
STEMS = ["main", "app", "index", "config", "utils", "server", "settings", "setup", "core", "handler", "api", "models"]
EXTRINSIC = {
    "fr": ["{n} avertissements", "en {d} secondes", "ligne {n}", "{n} fichiers modifiés", "fichier {f} introuvable",
           "mémoire à {p} %", "{n} tests échoués", "sur le port {port}", "{n} Go libres sur le disque"],
    "en": ["{n} warnings", "in {d} seconds", "line {n}", "{n} files changed", "file {f} not found", "memory at {p}%",
           "{n} tests failed", "on port {port}", "{n} GB free on disk"],
}
ABSENT = {"fr": re.compile(r"pas dans l'historique|n'apparaît pas|aucune commande", re.I),
          "en": re.compile(r"not in the history|does not appear|no command", re.I)}
ABSENT_ANSWER = {"fr": "C'était {cmd}, terminée avec le code {n}.", "en": "It was {cmd}, it exited with code {n}."}
COMMANDS = ["npm test", "make build", "git push", "docker compose up", "pytest -q", "cargo build", "pip install -r requirements.txt"]


def lang_of(messages):
    return "fr" if messages[0]["content"].startswith("Tu ") else "en"


def context_of(messages):
    return "\n\n".join(m["content"] for m in messages[:-1] if m["role"] == "user")


def absent_in(value, ctx):
    return re.search(rf"(?<![\d.,]){re.escape(value)}(?![\d])", ctx) is None


def fresh_number(rng, ctx, low=2, high=99):
    for _ in range(50):
        n = str(rng.randint(low, high))
        if absent_in(n, ctx):
            return n
    return None


def token_at(text, i):
    return re.search(r"\S*$", text[:i]).group(0) + re.match(r"\S*", text[i:]).group(0)


def alter_number(rng, label, ctx):
    """Addresses are never altered: a changed private IP becomes a real public one."""
    cands = [m for m in NUM.finditer(label) if m.group(1) in ctx and not ADDRESS.search(token_at(label, m.start()))]
    if not cands:
        return None
    m = rng.choice(cands)
    v = m.group(1)
    for _ in range(30):
        if re.search(r"[.,]", v):
            head, sep, tail = re.split(r"([.,])", v, maxsplit=1)
            new = f"{head}{sep}{(int(tail) + rng.randint(1, 8)) % (10 ** len(tail)):0{len(tail)}d}"
            if rng.random() < 0.5:
                new = f"{int(head) + rng.randint(1, 3)}{sep}{tail}"
        else:
            n = int(v)
            new = str(max(0, n + rng.choice([-3, -2, -1, 1, 2, 3, 5, 10]) * max(1, n // 10)))
        if new != v and absent_in(new, ctx):
            return label[:m.start(1)] + new + label[m.end(1):]
    return None


def alter_code(rng, label, ctx):
    m = CODE.search(label)
    if not m:
        return None
    for new in rng.sample(["0", "1", "2", "3", "127", "130", "137", "255"], 8):
        if new != m.group(2) and absent_in(f"code {new}", ctx) and absent_in(f"({new})", ctx):
            return label[:m.start(2)] + new + label[m.end(2):]
    return None


def flip_status(rng, label, ctx, lang):
    for old, new in STATUS[lang]:
        m = re.search(rf"\b{re.escape(old)}\b", label)
        if m:
            return label[:m.start()] + new + label[m.end():]
    return None


def alter_file(rng, label, ctx):
    cands = [m for m in FILE.finditer(label) if m.group(0) in ctx]
    if not cands:
        return None
    m = rng.choice(cands)
    for stem in rng.sample(STEMS, len(STEMS)):
        new = f"{stem}.{m.group(2)}"
        if stem != m.group(1) and new not in ctx:
            return label[:m.start()] + new + label[m.end():]
    return None


def extrinsic(rng, label, ctx, lang):
    if ABSENT[lang].search(label):
        cmd = next((c for c in rng.sample(COMMANDS, len(COMMANDS)) if c not in ctx), None)
        n = fresh_number(rng, ctx, 1, 9)
        return ABSENT_ANSWER[lang].format(cmd=cmd, n=n) if cmd and n else None
    tpl = rng.choice(EXTRINSIC[lang])
    vals = {"n": fresh_number(rng, ctx), "d": None, "p": fresh_number(rng, ctx, 40, 98),
            "port": fresh_number(rng, ctx, 3000, 9999), "f": None}
    d = f"{rng.randint(1, 9)}{',' if lang == 'fr' else '.'}{rng.randint(1, 9)}"
    vals["d"] = d if d not in ctx else None
    vals["f"] = next((f"{s}.{e}" for s in rng.sample(STEMS, len(STEMS)) for e in ("yaml", "json", "py")
                      if f"{s}.{e}" not in ctx), None)
    needed = re.findall(r"\{(\w+)\}", tpl)
    if any(vals[k] is None for k in needed):
        return None
    clause = tpl.format(**vals)
    body = label.rstrip()
    end = "." if body.endswith(".") else ""
    body = body.rstrip(".").rstrip()
    sep = ", " if body else ""
    return f"{body}{sep}{clause}{end}" if body else clause[0].upper() + clause[1:] + "."


INTRINSIC = ("number", "code", "status", "file")


def inject(rng, messages, want_extrinsic):
    label, ctx, lang = messages[-1]["content"], context_of(messages), lang_of(messages)
    ops = [("extrinsic", lambda: extrinsic(rng, label, ctx, lang))]
    intr = [("number", lambda: alter_number(rng, label, ctx)), ("code", lambda: alter_code(rng, label, ctx)),
            ("status", lambda: flip_status(rng, label, ctx, lang)), ("file", lambda: alter_file(rng, label, ctx))]
    rng.shuffle(intr)
    # no fallback across kinds: the intrinsic/extrinsic balance stays at --extrinsic-share
    for name, fn in (ops if want_extrinsic else intr):
        out = fn()
        if out and out.strip() != label.strip():
            return name, out
    return None, None


def build(rows, n, fr_share, rng, ex_share):
    quota = {"fr": round(n * fr_share), "en": n - round(n * fr_share)}
    got = collections.Counter()
    out = []
    for msgs in rows:
        lang = lang_of(msgs)
        if got[lang] >= quota[lang] or not msgs[-1]["content"].strip():
            continue
        op, rej = inject(rng, msgs, rng.random() < ex_share)
        if op is None:
            continue
        got[lang] += 1
        out.append({"prompt": msgs[:-1], "chosen": msgs[-1]["content"], "rejected": rej, "op": op, "lang": lang})
    return out


def load(path):
    seen, rows = set(), []
    for line in open(path, encoding="utf-8"):
        msgs = json.loads(line)["messages"]
        k = "\x00".join(m["content"] for m in msgs[:-1])
        if k not in seen:
            seen.add(k)
            rows.append(msgs)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--train", type=int, default=800)
    ap.add_argument("--val", type=int, default=60)
    ap.add_argument("--fr-share", type=float, default=2 / 3)
    ap.add_argument("--extrinsic-share", type=float, default=0.4)
    ap.add_argument("--seed", type=int, default=20260928)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for split, n in (("train", a.train), ("val", a.val)):
        rows = load(a.data / f"{split}.jsonl")
        rng.shuffle(rows)
        pairs = build(rows, n, a.fr_share, rng, a.extrinsic_share)
        with open(a.out / f"pairs-{split}.jsonl", "w", encoding="utf-8") as f:
            for p in pairs:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        counts[split] = {"prompts_unique": len(rows), "pairs": len(pairs),
                         "by_lang": dict(collections.Counter(p["lang"] for p in pairs)),
                         "by_op": dict(collections.Counter(p["op"] for p in pairs))}
    json.dump(counts, open(a.out / "inject-counts.json", "w"), indent=1)
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
