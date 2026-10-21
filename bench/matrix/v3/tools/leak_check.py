#!/usr/bin/env python3
"""Leak check v3-fp1 (DESIGN.md section 7): bench v3 cases against training corpora, by hashes only.

    python3 leak_check.py prints <out.json> <cases.jsonl> [...]           # on the Mac: hashes only
    python3 leak_check.py scan <prints.json> <out.json> <corpus.jsonl> [...]  # on the corpus host
    python3 leak_check.py local <prints.json> <out.json>                   # Speak Bench v1 + bench v2
    python3 leak_check.py drop <prints.json> <in.jsonl> <out.jsonl>        # on the corpus host: rows without leak

The corpus never leaves its host: `scan` is copied there with the prints (hashes of normalized
lines and 5-word shingles), and only case ids and scores come back. Each case is fingerprinted
twice: raw output and production input (digest), headers removed; the corpus side uses every
user message of an example, headers removed. A case is rejected if line Jaccard >= 0.5, or
shingle Jaccard >= 0.6, or same normalized command and line Jaccard >= 0.3. The scan also counts
corpus lines carrying the v3 canary. `drop` writes the rows of a corpus file that reject no case.

SPDX-License-Identifier: MIT
"""

import hashlib
import json
import re
import sys
from collections import defaultdict

CANARY = "steph-bench-v3-canary-6e21d5e02bf0"
HEADER = re.compile(r"^(commande|statut|durée|duree|sortie|command|status|duration|output|historique( de la session)?|history|"
                    r"session history|question)\s*:", re.I)
CMD_LINE = re.compile(r"^(?:commande|command)\s*:\s*(.+)$", re.I | re.M)
HEX = re.compile(r"\b[0-9a-f]{6,}\b")
PATH = re.compile(r"(?:~|\.{1,2})?(?:/[\w.@+-]+)+/?")
DIGIT = re.compile(r"\d")
SPACE = re.compile(r"\s+")


def norm_line(line):
    s = line.lower()
    s = HEX.sub("h", s)
    s = PATH.sub("/p", s)
    s = DIGIT.sub("0", s)
    return SPACE.sub(" ", s).strip()


PLACEHOLDERS = {"(aucune sortie)", "(no output)"}


def body_lines(text):
    return [n for n in (norm_line(l) for l in text.split("\n") if not HEADER.match(l.strip()))
            if n and n not in PLACEHOLDERS]


def fp(text):
    lines = body_lines(text)
    words = " ".join(lines).split()
    return ({hashlib.sha1(l.encode()).hexdigest()[:12] for l in lines},
            {hashlib.sha1(" ".join(words[i:i + 5]).encode()).hexdigest()[:12] for i in range(max(0, len(words) - 4))})


def norm_cmd(cmd):
    parts = [p for p in cmd.replace("sudo ", "").split() if not p.startswith("-")]
    if len(parts) > 1 and not re.search(r"[/.=]", parts[1]):
        return " ".join(parts[:2])
    return parts[0] if parts else ""


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def case_prints(case):
    texts = []
    if case["task"] == "summary":
        texts.append(case["output_raw"])
        cmds = [case["cmd"]]
    else:
        texts.append("\n".join(h["output_raw"] for h in case["history"]))
        cmds = []
    for lang in ("fr", "en"):
        texts.append("\n".join(m["content"] for m in case["input"][lang] if m["role"] == "user"))
    reps = []
    for t in texts:
        lines, sh = fp(t)
        reps.append({"lines": sorted(lines), "shingles": sorted(sh)})
    return {"id": case["id"], "cmds": [norm_cmd(c) for c in cmds], "reps": reps}


def prints(out, paths):
    cases = [json.loads(l) for p in paths for l in open(p) if l.strip()]
    json.dump([case_prints(c) for c in cases], open(out, "w"))
    print(f"{len(cases)} cases fingerprinted")


def example_of_line(line):
    """(user text, has canary) of one corpus line, None when it is not JSON."""
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        return None
    msgs = d.get("messages") or (d["prompt"] if isinstance(d.get("prompt"), list) else [])  # paires DPO : prompt
    users = "\n".join(m.get("content", "") for m in msgs if m.get("role") == "user")
    if not msgs and "output" in d:  # enregistrement brut (sortie de bac à sable) : commande et sortie
        users = f"Commande : {d.get('cmd', '')}\n{d['output']}"
    return users, CANARY in line


def examples_from_jsonl(path):
    for line in open(path, errors="replace"):
        if line.strip() and (ex := example_of_line(line)) is not None:
            yield ex


def scan_texts(case_prints_list, texts):
    """texts: iterable of (text, has_canary). Returns per case the max scores and verdict."""
    ex_lines, ex_sh, ex_cmds, canary = [], [], [], 0
    index = defaultdict(set)
    for t, has_canary in texts:
        canary += has_canary
        lines, sh = fp(t)
        k = len(ex_lines)
        ex_lines.append(lines)
        ex_sh.append(sh)
        ex_cmds.append({norm_cmd(c) for c in CMD_LINE.findall(t)})
        for h in lines:
            index[h].add(k)
    res = []
    for cp in case_prints_list:
        best = {"line": 0.0, "shingle": 0.0, "same_cmd_line": 0.0}
        for rep in cp["reps"]:
            lines, sh = set(rep["lines"]), set(rep["shingles"])
            cand = set().union(*(index.get(h, set()) for h in lines)) if lines else set()
            for k in cand:
                j = jac(lines, ex_lines[k])
                best["line"] = max(best["line"], j)
                best["shingle"] = max(best["shingle"], jac(sh, ex_sh[k]))
                if set(cp["cmds"]) & ex_cmds[k]:
                    best["same_cmd_line"] = max(best["same_cmd_line"], j)
        rejected = best["line"] >= 0.5 or best["shingle"] >= 0.6 or best["same_cmd_line"] >= 0.3
        res.append({"id": cp["id"], **{k: round(v, 3) for k, v in best.items()}, "rejected": rejected})
    return {"examples": len(ex_lines), "canary_lines": canary, "cases": res}


def drop(prints_path, src, out):
    """Copies the rows of src that reject no case; returns counts and the case ids that were hit."""
    cps = json.load(open(prints_path))
    rows = [line for line in open(src, encoding="utf-8") if line.strip()]
    bad, hit = set(), set()
    for k, line in enumerate(rows):
        ex = example_of_line(line)
        if ex is None:
            continue
        cases = scan_texts(cps, [ex])["cases"]
        ids = [c["id"] for c in cases if c["rejected"]]
        if ids:
            bad.add(k)
            hit.update(ids)
    with open(out, "w", encoding="utf-8") as f:
        f.writelines(line for k, line in enumerate(rows) if k not in bad)
    return {"rows": len(rows), "dropped": len(bad), "kept": len(rows) - len(bad), "cases": sorted(hit)}


def main():
    mode = sys.argv[1]
    if mode == "drop":
        print(json.dumps(drop(sys.argv[2], sys.argv[3], sys.argv[4])))
        return 0
    if mode == "prints":
        prints(sys.argv[2], sys.argv[3:])
        return 0
    cps = json.load(open(sys.argv[2]))
    if mode == "scan":
        texts = (t for p in sys.argv[4:] for t in examples_from_jsonl(p))
    else:
        from pathlib import Path
        repo = Path(__file__).resolve().parents[4]
        texts = []
        for p in sorted((repo / "benchmark" / "data" / "v1").rglob("*.jsonl")):
            for line in open(p):
                if line.strip():
                    d = json.loads(line)
                    texts.append((json.dumps(d, ensure_ascii=False).replace("\\n", "\n"), False))
        for c in json.load(open(repo / "bench" / "matrix" / "cases_compact_granite200_train.json")):
            texts.append(("\n".join(m["content"] for m in c["messages"] if m["role"] == "user"), False))
    r = scan_texts(cps, texts)
    json.dump(r, open(sys.argv[3], "w"))
    rej = [c["id"] for c in r["cases"] if c["rejected"]]
    top = sorted(r["cases"], key=lambda c: -c["line"])[:5]
    print(json.dumps({"examples": r["examples"], "canary_lines": r["canary_lines"], "rejected": rej,
                      "max_line": max((c["line"] for c in r["cases"]), default=0),
                      "max_shingle": max((c["shingle"] for c in r["cases"]), default=0),
                      "top_line": [(c["id"], c["line"], c["shingle"], c["same_cmd_line"]) for c in top]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
