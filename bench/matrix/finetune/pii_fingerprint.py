#!/usr/bin/env python3
"""Recherche des termes privés par empreinte salée, sans que la liste quitte le Mac (P21).

Sur le Mac :  python3 pii_fingerprint.py make --out fp.json [--names FICHIER]
Au labo :     python3 pii_fingerprint.py scan --fp fp.json fichiers... [--out hits.json]

`make` lit ~/.config/steph/pii_names.tsv (ou STEPH_PII_NAMES), tire un sel aléatoire et
écrit sha256(sel + forme) pour chaque forme courante d'un terme : minuscules, séparateurs
« - . _ espace » interchangés ou retirés. Chaque terme n'est désigné que par son rang dans
la liste (n01, n02...). `scan` rejoue ces formes sur les jetons d'un JSONL (minuscules,
accents retirés, mêmes frontières alphanumériques qu'`audit_pii.py`) et ne rend que
fichier, ligne, champ et identifiant : jamais le texte trouvé.

SPDX-License-Identifier: MIT
"""

import argparse
import collections
import hashlib
import json
import os
import re
import secrets
import sys
import unicodedata

DEFAULT_NAMES = os.path.expanduser("~/.config/steph/pii_names.tsv")
SEPARATORS = ("-", ".", "_", " ", "")
_RUN = re.compile(r"[a-z0-9]+")
_MAX_CANDIDATE = 64


def _digest(salt, text):
    return hashlib.sha256(bytes.fromhex(salt) + text.encode("utf-8")).hexdigest()


def _fold(text):
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _terms(path):
    terms = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.rstrip("\n")
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            term = raw.split("\t")[0].strip()
            if term:
                terms.append(term)
    return terms


def make_fingerprints(names_path, salt=None):
    salt = salt or secrets.token_hex(32)
    hashes = {}
    max_runs = 1
    for rank, term in enumerate(_terms(names_path), 1):
        runs = _RUN.findall(_fold(term))
        max_runs = max(max_runs, len(runs))
        forms = {_fold(term)} | {sep.join(runs) for sep in SEPARATORS}
        for form in forms:
            hashes[_digest(salt, form)] = f"n{rank:02d}"
    return {"salt": salt, "max_runs": max_runs, "hashes": hashes}


def _candidates(text, max_runs):
    runs = [(m.start(), m.end()) for m in _RUN.finditer(text)]
    for i, (start, end) in enumerate(runs):
        yield text[start:end]
        for j in range(i + 1, min(i + max_runs, len(runs))):
            gap = text[runs[j - 1][1]:runs[j][0]]
            if len(gap) != 1:
                break
            end = runs[j][1]
            if end - start > _MAX_CANDIDATE:
                break
            yield text[start:end]


def scan_text(text, fp, cache=None):
    cache = {} if cache is None else cache
    found = []
    for variant in {text.lower(), _fold(text)}:
        for cand in _candidates(variant, fp["max_runs"]):
            if cand not in cache:
                cache[cand] = fp["hashes"].get(_digest(fp["salt"], cand))
            if cache[cand]:
                found.append(cache[cand])
    return sorted(set(found))


def _strings(obj, path=""):
    if isinstance(obj, str):
        yield path or "<value>", obj
    elif isinstance(obj, dict):
        role = obj.get("role") if isinstance(obj.get("role"), str) else None
        for key, value in obj.items():
            if role and key == "content":
                yield from _strings(value, f"{path}({role})" if path else f"({role})")
            else:
                yield from _strings(value, f"{path}.{key}" if path else str(key))
    elif isinstance(obj, list):
        for k, value in enumerate(obj):
            yield from _strings(value, f"{path}[{k}]")


def scan_file(path, fp, cache=None):
    cache = {} if cache is None else cache
    hits = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for lineno, raw in enumerate(handle, 1):
            try:
                fields = list(_strings(json.loads(raw)))
            except json.JSONDecodeError:
                fields = [("<raw>", raw)]
            for field, text in fields:
                for ident in scan_text(text, fp, cache):
                    hits.append({"line": lineno, "field": field, "id": ident})
            if len(cache) > 5_000_000:
                cache.clear()
    return hits


def _cmd_make(args):
    if not os.path.exists(args.names):
        print(f"liste de noms introuvable : {args.names}", file=sys.stderr)
        return 2
    fp = make_fingerprints(args.names)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(fp, handle)
    print(f"{len(set(fp['hashes'].values()))} termes, {len(fp['hashes'])} empreintes -> {args.out}")
    return 0


def _cmd_scan(args):
    with open(args.fp, encoding="utf-8") as handle:
        fp = json.load(handle)
    report = {}
    cache = {}
    total = 0
    for path in args.files:
        try:
            hits = scan_file(path, fp, cache)
        except OSError as exc:
            print(f"{path} : illisible ({exc.strerror})", file=sys.stderr)
            continue
        total += len(hits)
        report[path] = hits
        if hits:
            ids = collections.Counter(h["id"] for h in hits)
            print(f"{path} : {len(hits)} ({', '.join(f'{k}x{v}' for k, v in sorted(ids.items()))})")
    print(f"TOTAL : {total} sur {len(args.files)} fichier(s)")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle)
    return 1 if total else 0


def main():
    parser = argparse.ArgumentParser(description="Termes privés cherchés par empreinte salée.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    make = sub.add_parser("make")
    make.add_argument("--names", default=os.environ.get("STEPH_PII_NAMES", DEFAULT_NAMES))
    make.add_argument("--out", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--fp", required=True)
    scan.add_argument("--out")
    scan.add_argument("files", nargs="+")
    args = parser.parse_args()
    return _cmd_make(args) if args.cmd == "make" else _cmd_scan(args)


if __name__ == "__main__":
    sys.exit(main())
