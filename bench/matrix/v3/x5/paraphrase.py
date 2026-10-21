#!/usr/bin/env python3
"""X5, part 1: robustness of the v3 fact scorer to paraphrases (dev split only).

    python3 paraphrase.py prep  <tasks.jsonl> [--holdout]      stratified dev sample, generator prompts
    python3 paraphrase.py gen   <tasks.jsonl> <out.jsonl> [--ports 8971,8972]   (stdlib only, resumable)
    python3 paraphrase.py eval  <out.jsonl> [--audit audit.json] [--json res.json]

The generator (Qwen3.5 27B) sees the production input and the reference, never the fact regexes:
the paraphrases must not be tailored to the scorer. Per evaluation (case, language): 5 correct
rewordings (J1-J5) and 5 wrong sentences (F1-F5: two changed facts, one invented detail, one
omission of the key fact, one contradiction). A correct sentence scored below 100 is a false
negative; a wrong sentence scored 100 is a false positive.

SPDX-License-Identifier: MIT
"""

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"

PER_FAMILY = 7
QA_EVALS = 20
HOLDOUT_PER_FAMILY = 2
HOLDOUT_QA = 6
WRONG_KINDS = {"F1": "changed", "F2": "changed", "F3": "invented", "F4": "omitted", "F5": "contradiction"}
LANG_NAME = {"fr": "French", "en": "English"}

SYSTEM = ("You write test sentences for a benchmark of short spoken summaries of terminal output. "
          "Answer only with the requested lines, no markdown, no comments.")

PROMPT = """Input the assistant read:
<<<
{context}
>>>
Reference answer (correct, in {lang_name}): "{reference}"

Write in {lang_name}, each sentence at most {max_words} words, one per line, no quotes, no markdown.

J1 to J5: five CORRECT rewordings of the reference. Keep every piece of information of the reference (every number, name, file, line, value) and add nothing that is not in the input. Vary them strongly: different word order, synonyms, a different sentence shape. In at least two of them, write whole numbers in words instead of digits (for example "{three}"). In one of them, give the facts in a different order.

F1 to F5: five WRONG but plausible sentences, in the same style:
F1: change one key number or name to another plausible value, preferably one that appears elsewhere in the input.
F2: change a different key fact in the same way.
F3: keep the facts of the reference but add one precise, plausible detail that is NOT in the input.
F4: leave out the most important fact of the reference and keep the rest.
F5: state the opposite for one fact (for example passed instead of failed, found instead of absent, success instead of error).

Answer exactly in this format:
J1: ...
J2: ...
J3: ...
J4: ...
J5: ...
F1: ...
F2: ...
F3: ...
F4: ...
F5: ..."""


def load_dev():
    cases = []
    for f in sorted((TOOLS.parent / "cases" / "dev").glob("*.jsonl")):
        cases += [json.loads(l) for l in open(f) if l.strip()]
    return cases


def rank(case_id):
    return hashlib.sha256(("x5-paraphrase:" + case_id).encode()).hexdigest()


def sample(cases, holdout=False):
    """(case, lang) pairs: PER_FAMILY summaries per family, QA_EVALS questions, languages alternated.
    holdout: the next HOLDOUT_PER_FAMILY summaries and HOLDOUT_QA questions by rank, never in the
    first sample, to measure the fixes on sentences they were not fitted on."""
    picked = []
    by_family = {}
    for c in cases:
        by_family.setdefault((c["task"], c["family"]), []).append(c)
    for (task, family), cs in sorted(by_family.items()):
        n = QA_EVALS if task == "qa" else PER_FAMILY
        ranked = sorted(cs, key=lambda c: rank(c["id"]))
        chosen = ranked[n:n + (HOLDOUT_QA if task == "qa" else HOLDOUT_PER_FAMILY)] if holdout else ranked[:n]
        for i, c in enumerate(chosen):
            picked.append((c, ("fr", "en")[(i + int(rank(family)[:2], 16)) % 2]))
    return picked


def context(case, lang):
    users = [m["content"] for m in case["input"][lang] if m["role"] == "user"]
    return "\n\n".join(users)


def prep(path, holdout=False):
    rows = []
    for c, lang in sample(load_dev(), holdout):
        prompt = PROMPT.format(context=context(c, lang), lang_name=LANG_NAME[lang], reference=c["reference"][lang],
                               max_words=c["max_words"], three="trois" if lang == "fr" else "three")
        rows.append({"id": f"{c['id']}@{lang}", "family": c["family"], "task": c["task"], "lang": lang,
                     "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} tasks")


def post(port, messages, max_tokens=500):
    body = json.dumps({"messages": messages, "max_tokens": max_tokens, "temperature": 0.7, "top_p": 0.9,
                       "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False}}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", body,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.load(r)["choices"][0]["message"]["content"]


LINE = re.compile(r"^\s*\**\s*([JF][1-5])\s*\**\s*[:.)-]\s*(.+?)\s*$")


def parse(text):
    out = {}
    for line in text.splitlines():
        m = LINE.match(line)
        if m and m.group(1) not in out:
            out[m.group(1)] = m.group(2).strip().strip("\"«»“”").strip()
    return out


def gen(tasks_path, out_path, ports):
    tasks = [json.loads(l) for l in open(tasks_path)]
    done = {json.loads(l)["id"] for l in open(out_path)} if os.path.exists(out_path) else set()
    todo = [t for t in tasks if t["id"] not in done]

    local, lock, free = threading.local(), threading.Lock(), list(ports)

    def one(t):
        if not hasattr(local, "port"):
            with lock:
                local.port = free.pop(0)
        for attempt in range(3):
            try:
                raw = post(local.port, t["messages"])
                lines = parse(raw)
                if len(lines) == 10:
                    return {"id": t["id"], "raw": raw, "lines": lines}
            except Exception as e:  # noqa: BLE001 - retried, then recorded
                raw = f"error: {e}"
            time.sleep(2)
        return {"id": t["id"], "raw": raw, "lines": parse(raw) if not raw.startswith("error") else {}}

    with ThreadPoolExecutor(len(ports)) as ex, open(out_path, "a") as f:
        for i, r in enumerate(ex.map(one, todo), 1):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{i}/{len(todo)} {r['id']} {len(r['lines'])} lignes", flush=True)


def evaluate(out_path, audit_path=None, as_json=None):
    sys.path.insert(0, str(TOOLS))
    import score_v3
    cases = {c["id"]: c for c in load_dev()}
    audit = json.load(open(audit_path)) if audit_path else {}
    rows, rejected = [], 0
    for r in map(json.loads, open(out_path)):
        case_id, lang = r["id"].rsplit("@", 1)
        c = cases[case_id]
        for key, text in sorted(r["lines"].items()):
            label = audit.get(f"{r['id']}#{key}", "ok")
            if label == "reject":
                rejected += 1
                continue
            s = score_v3.score_answer(c, lang, text)
            rows.append({"id": r["id"], "key": key, "family": c["family"], "task": c["task"], "lang": lang, "audit": label,
                         "correct": key.startswith("J"), "kind": "correct" if key.startswith("J") else WRONG_KINDS[key],
                         "score": s, "text": text,
                         "too_long": len(score_v3.clean(text).split()) > c["max_words"]})
    report = {"sentences": len(rows) + rejected, "rejected_by_audit": rejected, **summarize(rows)}
    if as_json:
        json.dump({"summary": report, "rows": rows}, open(as_json, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


def rate(xs):
    return {"n": len(xs), "rate": round(100 * sum(xs) / len(xs), 1) if xs else None}


def summarize(rows):
    """False negative: correct sentence below 1 (length penalty set apart); false positive: wrong at 1.

    fp_key: false positives on a changed or omitted fact that the facts are meant to check (audit
    label not `secondary`); inventions and contradictions are a structural limit of fact regexes."""
    good = [r for r in rows if r["correct"]]
    bad = [r for r in rows if not r["correct"]]
    fn = lambda rs: [r["score"] < 1.0 and not (r["too_long"] and r["score"] >= 0.8 - 1e-9) for r in rs]  # noqa: E731
    fp = lambda rs: [r["score"] >= 1.0 - 1e-9 for r in rs]  # noqa: E731
    out = {"false_negative": rate(fn(good)), "false_negative_with_length": rate([r["score"] < 1.0 for r in good]),
           "false_positive": rate(fp(bad)),
           "fp_key": rate(fp([r for r in bad if r["kind"] in ("changed", "omitted") and r["audit"] != "secondary"])),
           "fp_secondary": rate(fp([r for r in bad if r["audit"] == "secondary"])), "by_kind": {}, "by_lang": {}, "by_task": {}, "by_family": {},
           "cases_with_fn": sorted({r["id"] for r, x in zip(good, fn(good)) if x})}
    for kind in sorted({r["kind"] for r in bad}):
        out["by_kind"][kind] = rate(fp([r for r in bad if r["kind"] == kind]))
    for axis, key in (("by_lang", "lang"), ("by_task", "task"), ("by_family", "family")):
        for v in sorted({r[key] for r in rows}):
            out[axis][v] = {"fn": rate(fn([r for r in good if r[key] == v])),
                            "fp": rate(fp([r for r in bad if r[key] == v])),
                            "fp_key": rate(fp([r for r in bad if r[key] == v and r["kind"] in ("changed", "omitted")
                                               and r["audit"] != "secondary"]))}
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep")
    p.add_argument("tasks")
    p.add_argument("--holdout", action="store_true")
    g = sub.add_parser("gen")
    g.add_argument("tasks")
    g.add_argument("out")
    g.add_argument("--ports", default="8971,8972", help="one llama-server (parallel 1) per worker thread")
    e = sub.add_parser("eval")
    e.add_argument("out")
    e.add_argument("--audit")
    e.add_argument("--json")
    a = ap.parse_args()
    if a.cmd == "prep":
        prep(a.tasks, a.holdout)
    elif a.cmd == "gen":
        gen(a.tasks, a.out, [int(p) for p in a.ports.split(",")])
    else:
        evaluate(a.out, a.audit, a.json)


if __name__ == "__main__":
    main()
