"""r3t5_public_corpus.py <pub_dir> <frozen_src_dir> <out_dir>

Public text used only to count Granite tokens (R3-T5): tldr-pages EN+FR (CC BY 4.0),
python-docs-fr .po (msgid PSF docs, msgstr CC0), Project Gutenberg FR/EN (public domain),
CPython stdlib sources (PSF-2.0), T7 and R2-C4 public sandbox corpora, steph production
prompts. Never the bench, never the personal corpus.

Each unit goes to selection or control by a stable hash (1 in 10 to control), so the
tokenization check runs on strings the vocabulary was not chosen from.
Writes selection.jsonl and control.jsonl ({"src", "text"}).

SPDX-License-Identifier: MIT
"""
import glob
import hashlib
import json
import os
import re
import sys

pub, frozen, out = sys.argv[1:4]
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
units = []


def add(src, text):
    text = text.strip("\n")
    if text.strip():
        units.append((src, text))


for lang, root in (("en", "pages"), ("fr", "pages.fr")):
    for plat in ("common", "linux", "osx"):
        for f in sorted(glob.glob(f"{pub}/tldr/{root}/{plat}/*.md")):
            add(f"tldr-{lang}", open(f, encoding="utf-8").read())

po_str = re.compile(r'^(msgid|msgstr) (".*")\s*$|^(".*")\s*$')
for f in sorted(glob.glob(f"{pub}/python-docs-fr/**/*.po", recursive=True)):
    cur, kind = [], None
    for line in open(f, encoding="utf-8"):
        m = po_str.match(line)
        if not m:
            if cur and kind:
                add(f"pydocs-{'en' if kind == 'msgid' else 'fr'}", "".join(json.loads(s) for s in cur))
            cur, kind = [], None
            continue
        if m.group(1):
            if cur and kind:
                add(f"pydocs-{'en' if kind == 'msgid' else 'fr'}", "".join(json.loads(s) for s in cur))
            kind, cur = m.group(1), [m.group(2)]
        else:
            cur.append(m.group(3))

for f in sorted(glob.glob(f"{pub}/pg*.txt")):
    body = open(f, encoding="utf-8-sig").read()
    s, e = body.find("*** START OF"), body.find("*** END OF")
    body = body[body.find("\n", s) + 1:e] if s >= 0 and e > s else body
    for para in re.split(r"\n\s*\n", body):
        add("gutenberg", para)

pylib = glob.glob("/opt/homebrew/opt/python@3.13/Frameworks/Python.framework/Versions/3.13/lib/python3.13/*.py")
for f in sorted(pylib):
    lines = open(f, encoding="utf-8", errors="replace").read().split("\n")
    for i in range(0, len(lines), 40):
        add("cpython", "\n".join(lines[i:i + 40]))

public = sorted(glob.glob(f"{REPO}/bench/matrix/results/finetune/loop/round-1/t7/public_t7.*.jsonl")
                + glob.glob(f"{REPO}/bench/matrix/results/finetune/loop/round-2/r2c4-p*/public_p*.jsonl")
                + glob.glob(f"{REPO}/bench/matrix/results/finetune/loop/round-2/r2c4-p3/data/public_p3*.jsonl"))
for f in public:
    for line in open(f, encoding="utf-8"):
        row = json.loads(line)
        for m in row.get("messages", []):
            add("sandbox", m["content"])
        for k in ("output", "raw_output", "stdout", "label", "summary"):
            if isinstance(row.get(k), str):
                add("sandbox", row[k])

for f in [f"{frozen}/src/steph/prompts.py", f"{REPO}/bench/matrix/finetune/train_system_prompt.txt",
          f"{REPO}/bench/matrix/finetune/train_system_prompt.en.txt"]:
    add("steph-prompts", open(f, encoding="utf-8").read())

seen = set()
os.makedirs(out, exist_ok=True)
counts = {}
with open(f"{out}/selection.jsonl", "w") as sel, open(f"{out}/control.jsonl", "w") as ctl:
    for src, text in units:
        h = hashlib.sha256(text.encode()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        to_ctl = src != "steph-prompts" and int(h[:8], 16) % 10 == 0
        (ctl if to_ctl else sel).write(json.dumps({"src": src, "text": text}, ensure_ascii=False) + "\n")
        c = counts.setdefault(src, [0, 0])
        c[1 if to_ctl else 0] += 1
print(json.dumps({"units": len(seen), "by_source_selection_control": counts, "public_files": [os.path.relpath(p, REPO) for p in public]}, ensure_ascii=False, indent=1))
