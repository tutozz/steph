#!/usr/bin/env python3
"""Build data/v1/<lang>/<split>.jsonl from the case sources in tools/cases/.

    python3 benchmark/tools/build_dataset.py            # write the dataset
    python3 benchmark/tools/build_dataset.py --check    # write nothing, report problems
    python3 benchmark/tools/build_dataset.py --check --only tests_cases

A source module exposes CASES, a list of dicts. Any text field may be a plain value
(shared by both languages) or {"en": ..., "fr": ...}.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
DATA = BENCH / "data" / "v1"
LANGS = ("en", "fr", "de", "es", "pt", "ru")
CATEGORIES = ["build-failure", "runtime-error", "tests", "git", "packages", "network", "disks", "memory",
              "hardware", "containers", "long-lists", "long-truncated", "history-qa"]
FIELDS = ["id", "lang", "split", "category", "origin", "task", "cmd", "exit", "duration", "output", "history",
          "question", "expected", "forbidden", "reference", "max_words", "notes", "canary"]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = load("termspeak_run", BENCH / "run.py")
validate = load("termspeak_validate", HERE / "validate.py")
SCHEMA = json.loads((DATA / "schema.json").read_text(encoding="utf-8"))
CANARY = SCHEMA["properties"]["canary"]["const"]
CONFIG = run.load_config(DATA)


def sources(only: str = "") -> list:
    mods = sorted(p for p in (HERE / "cases").glob("*.py") if not p.name.startswith("_"))
    out = []
    for path in mods:
        if only and path.stem != only:
            continue
        for src in load(f"termspeak_cases_{path.stem}", path).CASES:
            out.append({**src, "_module": path.stem})
    return out


def localize(value, lang: str):
    """A dict keyed only by language codes is a translation map: pick `lang`, falling back
    to English when a language has no translation for that field (untranslated tool output,
    or a fact/question never captured in that language). Any other dict is a plain value."""
    if isinstance(value, dict) and value and set(value) <= set(LANGS):
        return value[lang] if lang in value else value["en"]
    return value


def materialize(src: dict, lang: str) -> dict:
    case = {k: localize(v, lang) for k, v in src.items() if not k.startswith("_")}
    case["lang"] = lang
    case.setdefault("forbidden", [])
    case.setdefault("max_words", CONFIG["scoring"]["max_words"][case["task"]])
    case["canary"] = CANARY
    return {k: case[k] for k in FIELDS if k in case} | {k: v for k, v in case.items() if k not in FIELDS}


def build(only: str = "") -> dict:
    srcs = sources(only)
    srcs.sort(key=lambda s: (CATEGORIES.index(s["category"]) if s.get("category") in CATEGORIES else 99, s["id"]))
    return {lang: [materialize(s, lang) for s in srcs] for lang in LANGS}


def render(lang: str) -> dict:
    cases = build()[lang]
    return {split: "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases if c["split"] == split)
            for split in run.SPLITS}


def problems(built: dict) -> list:
    out = []
    ids = [c["id"] for c in built["en"]]
    out += [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    scoring, prompts = CONFIG["scoring"], CONFIG["prompts"]
    for lang, cases in built.items():
        for c in cases:
            tag = f"{lang}:{c.get('id')}"
            out += [f"{tag} schema {e}" for e in validate.validate(c, SCHEMA)]
            if validate.validate(c, SCHEMA):
                continue
            n = run.source_lines(c)
            if not 5 <= n <= 400:
                out.append(f"{tag} {n} output lines, need 5-400")
            res = run.score_case(c, c["reference"], scoring)
            if res["score"] != 1.0:
                out.append(f"{tag} reference scores {res}")
            for p in c["expected"] + c["forbidden"]:
                bare = re.sub(r"\\.", "", p)
                if bare != run.normalize(bare) or any(ch.isupper() for ch in bare):
                    out.append(f"{tag} pattern not normalized: {p}")
            prompt = "\n".join(m["content"] for m in run.build_messages(c, prompts))
            for num in re.findall(r"\d+(?:[.,:]\d+)*", c["reference"]):
                if num not in prompt and num.replace(",", ".") not in prompt:
                    out.append(f"{tag} reference number {num} absent from the model input")
    return out


def pii(built: dict) -> list:
    path = BENCH.parent / "bench" / "matrix" / "finetune" / "audit_pii.py"
    if not path.exists():
        return ["PII scanner not found"]
    audit = load("termspeak_audit_pii", path)
    names_path = os.environ.get("STEPH_PII_NAMES", audit.DEFAULT_NAMES)
    names = audit.load_names(names_path) if os.path.exists(names_path) else []

    def strings(v):
        if isinstance(v, str):
            yield v
        elif isinstance(v, dict):
            for x in v.values():
                yield from strings(x)
        elif isinstance(v, list):
            for x in v:
                yield from strings(x)

    out = []
    for lang, cases in built.items():
        for c in cases:
            found = audit.scan_text("\n".join(strings(c)), names)
            if found:
                out.append(f"{lang}:{c['id']} PII {sorted(set(found))}")
    return out


def stats_table(cases: list, fr: bool) -> str:
    head = ("| Catégorie | dev | test | réels anonymisés | synthétiques | total |" if fr
            else "| Category | dev | test | real-anonymized | synthetic | total |")
    rows = [head, "|---|---:|---:|---:|---:|---:|"]

    def line(name, sub):
        n = lambda key, val: sum(c[key] == val for c in sub)
        return (f"| {name} | {n('split', 'dev')} | {n('split', 'test')} | {n('origin', 'real-anonymized')} "
                f"| {n('origin', 'synthetic')} | {len(sub)} |")

    for cat in CATEGORIES:
        rows.append(line(cat, [c for c in cases if c["category"] == cat]))
    rows.append(line("**total**", cases))
    lines = [run.source_lines(c) for c in cases]
    rows.append("")
    rows.append(f"{len(cases)} cas par langue, sorties de {min(lines)} à {max(lines)} lignes (médiane "
                f"{sorted(lines)[len(lines) // 2]})." if fr else
                f"{len(cases)} cases per language, outputs of {min(lines)} to {max(lines)} lines "
                f"(median {sorted(lines)[len(lines) // 2]}).")
    return "\n".join(rows)


def update_markers(path: Path, marker: str, text: str) -> None:
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    body = path.read_text(encoding="utf-8")
    new = re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: f"{start}\n{text}\n{end}", body, flags=re.S)
    path.write_text(new, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", default="", help="one source module (file stem)")
    a = ap.parse_args()
    built = build(a.only)
    issues = problems(built) + pii(built)
    for issue in issues:
        print(issue)
    counts = {}
    for c in built["en"]:
        counts[c["category"]] = counts.get(c["category"], 0) + 1
    print(f"{len(built['en'])} cases per language; {json.dumps(counts)}; {len(issues)} problem(s)")
    if a.check or a.only:
        return 1 if issues else 0
    for lang in LANGS:
        for split, text in render(lang).items():
            path = DATA / lang / f"{split}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    for readme, fr in ((BENCH / "README.md", False), (BENCH / "README.fr.md", True), (BENCH / "data" / "README.md", False)):
        if readme.exists():
            update_markers(readme, "dataset-stats", stats_table(built["en"], fr))
    print(f"written to {DATA}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
