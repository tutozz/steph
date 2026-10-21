#!/usr/bin/env python3
"""Spoken-style pairwise judge of bench v3 (X5): which of two answers sounds better read aloud.

    python3 judge_style_v3.py run <harness.json> <out.json> --a <runA.json> --b <runB.json> [--ports 8971,8972]
    python3 judge_style_v3.py controls <controls.jsonl> <out.json> [--ports 8971,8972]
    python3 judge_style_v3.py report <out.json>

Second axis, beside the fact score (score_v3.py), never instead of it. The judge (Qwen3.5 27B)
compares two answers to the same input on four criteria: clarity through text-to-speech, most
useful fact first, concision, naturalness in the answer language; plus an overall verdict.
Each pair is judged in both orders (x shown as A, then as B); a verdict is kept only when it
names the same answer both times, otherwise it is a tie. Identical answers are a tie without a
call in `run`; `controls` sends them to the judge, to measure it.
Context shown: the production user message for a summary, the question for a history question.
The judge never sees which model wrote which answer.

SPDX-License-Identifier: MIT
"""

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from score import clean  # noqa: E402

CRITERIA = ("clarte", "ordre", "concision", "naturel", "global")
LANG_NAME = {"fr": "French", "en": "English"}

SYSTEM = """You judge short sentences that a screen reader assistant for blind developers says aloud after a terminal command. A text-to-speech voice reads the sentence; the listener cannot see the screen and hears it once. Before the sentence, the assistant has already said "success" or "failure" in code, so repeating the status adds nothing.

You compare two answers, A and B, to the same input. Judge only how well each one is phrased for the ear, not whether its facts are right: another check scores the facts. If both are equally good on a criterion, answer "=".

Criteria:
clarte: easy to understand when heard once through text-to-speech. Symbols, arrows, markdown, raw paths or code punctuation read aloud badly; plain words read well.
ordre: the most useful fact for the listener comes first, not after a preamble.
concision: says the useful facts with no filler, no repetition, nothing the listener does not need.
naturel: sounds like natural spoken {lang_name}, not like a log line or a word-for-word translation.
global: which answer you would rather hear.

Answer with one line of five symbols separated by spaces, in this order: clarte ordre concision naturel global. Each symbol is A, B or =. Example: A = A B A"""

USER = """Input the assistant read:
<<<
{context}
>>>
The answers are in {lang_name}.

A: {first}

B: {second}"""

GRAMMAR = 'root ::= v " " v " " v " " v " " v\nv ::= "A" | "B" | "="\n'
VERDICT = re.compile(r"^\s*([AB=])\s+([AB=])\s+([AB=])\s+([AB=])\s+([AB=])\s*$")


def build_messages(context, first, second, lang):
    return [{"role": "system", "content": SYSTEM.format(lang_name=LANG_NAME[lang])},
            {"role": "user", "content": USER.format(context=context, lang_name=LANG_NAME[lang], first=first, second=second)}]


def parse_verdict(text):
    m = VERDICT.match(text or "")
    return dict(zip(CRITERIA, m.groups())) if m else None


def ask(call, messages, tries=3):
    for _ in range(tries):
        try:
            v = parse_verdict(call(messages))
        except Exception:  # noqa: BLE001 - server hiccup, retried
            v = None
        if v:
            return v
    return None


def judge_pair(call, context, x, y, lang, skip_identical=False):
    """final[criterion] in {"x", "y", "="}; raw = [x shown as A, x shown as B]."""
    if skip_identical and " ".join(x.split()) == " ".join(y.split()):
        return {"identical": True, "error": False, "raw": [], "final": {k: "=" for k in CRITERIA},
                "unstable": {k: False for k in CRITERIA}}
    first = ask(call, build_messages(context, x, y, lang))
    second = ask(call, build_messages(context, y, x, lang))
    if first is None or second is None:
        return {"identical": False, "error": True, "raw": [first, second], "final": {k: "=" for k in CRITERIA},
                "unstable": {k: False for k in CRITERIA}}
    final, unstable = {}, {}
    for k in CRITERIA:
        a = {"A": "x", "B": "y", "=": "="}[first[k]]
        b = {"A": "y", "B": "x", "=": "="}[second[k]]
        final[k] = a if a == b else "="
        unstable[k] = a != b and "=" not in (a, b)
    return {"identical": False, "error": False, "raw": [first, second], "final": final, "unstable": unstable}


def position_bias(results, criterion="global"):
    decided = [raw[criterion] for r in results for raw in r.get("raw") or [] if raw and raw[criterion] != "="]
    first = sum(v == "A" for v in decided)
    return {"decided": len(decided), "first_wins": first,
            "first_share": round(100 * first / len(decided), 1) if decided else None}


def _rate(rs, criterion):
    agree = sum(r["final"][criterion] == r["expected"] for r in rs)
    return {"n": len(rs), "agree": agree, "rate": round(100 * agree / len(rs), 1) if rs else None}


def control_agreement(results, criterion="global"):
    return {"planted": _rate([r for r in results if r["expected"] != "="], criterion),
            "identical": _rate([r for r in results if r["expected"] == "="], criterion),
            "all": _rate(results, criterion)}


def tally(results):
    out = {}
    for k in CRITERIA:
        c = {v: sum(r["final"][k] == v for r in results) for v in ("x", "y", "=")}
        n = len(results)
        out[k] = {**c, "n": n, "net_x": round(100 * (c["x"] - c["y"]) / n, 1) if n else None}
    return out


def context_of(row):
    users = [m["content"] for m in row["messages"] if m["role"] == "user"]
    return users[0] if row.get("kind", "summary") == "summary" else users[-1]


def pairs_from_runs(harness, run_a, run_b):
    rows = {r["id"]: r for r in harness}
    a = {r["id"]: r.get("out") for r in json.load(open(run_a))["rows"]}
    b = {r["id"]: r.get("out") for r in json.load(open(run_b))["rows"]}
    pairs = []
    for rid in sorted(set(a) & set(b) & set(rows)):
        if a[rid] is None or b[rid] is None:
            continue
        pairs.append({"id": rid, "lang": rid.rsplit("@", 1)[1], "context": context_of(rows[rid]),
                      "x": clean(a[rid]), "y": clean(b[rid])})
    return pairs


def server_call(ports):
    """One llama-server per worker thread: both orders of a pair reuse the same prompt cache."""
    local, lock, free = threading.local(), threading.Lock(), list(ports)

    def call(messages):
        if not hasattr(local, "port"):
            with lock:
                local.port = free.pop(0) if free else ports[0]
        port = local.port
        body = json.dumps({"messages": messages, "max_tokens": 12, "temperature": 0.0, "grammar": GRAMMAR,
                           "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False}}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", body,
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.load(r)["choices"][0]["message"]["content"]
    return call


def run_pairs(pairs, out_path, call, threads, skip_identical):
    done = json.load(open(out_path)) if os.path.exists(out_path) else []
    seen = {r["id"] for r in done if not r.get("error")}
    done = [r for r in done if r["id"] in seen]
    todo = [p for p in pairs if p["id"] not in seen]

    def one(p):
        return {**p, **judge_pair(call, p["context"], p["x"], p["y"], p["lang"], skip_identical)}

    t0 = time.time()
    with ThreadPoolExecutor(threads) as ex:
        for i, r in enumerate(ex.map(one, todo), 1):
            done.append(r)
            if i % 20 == 0 or i == len(todo):
                json.dump(done, open(out_path, "w"), ensure_ascii=False)
                print(f"{i}/{len(todo)} {time.time() - t0:.0f} s", flush=True)
    json.dump(done, open(out_path, "w"), ensure_ascii=False)
    return done


def report(results):
    ok = [r for r in results if not r.get("error")]
    out = {"n": len(results), "errors": len(results) - len(ok), "identical": sum(bool(r.get("identical")) for r in ok),
           "unstable_global": sum(bool(r["unstable"]["global"]) for r in ok),
           "position_bias": {k: position_bias(ok, k) for k in CRITERIA}}
    if ok and "expected" in ok[0]:
        out["controls"] = {k: control_agreement(ok, k) for k in CRITERIA}
        kinds = sorted({r.get("kind", "") for r in ok})
        out["controls_by_kind"] = {kd: control_agreement([r for r in ok if r.get("kind", "") == kd])["all"] for kd in kinds}
    else:
        out["tally"] = tally(ok)
        for lang in ("fr", "en"):
            out[f"tally_{lang}"] = tally([r for r in ok if r["lang"] == lang])["global"]
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("harness")
    r.add_argument("out")
    r.add_argument("--a", required=True)
    r.add_argument("--b", required=True)
    c = sub.add_parser("controls")
    c.add_argument("controls")
    c.add_argument("out")
    for p in (r, c):
        p.add_argument("--ports", default="8971,8972", help="one llama-server per worker thread")
    rp = sub.add_parser("report")
    rp.add_argument("out")
    a = ap.parse_args()
    ports = [int(p) for p in getattr(a, "ports", "0").split(",")]
    if a.cmd == "run":
        res = run_pairs(pairs_from_runs(json.load(open(a.harness)), a.a, a.b), a.out, server_call(ports), len(ports), True)
    elif a.cmd == "controls":
        pairs = [json.loads(l) for l in open(a.controls) if l.strip()]
        res = run_pairs(pairs, a.out, server_call(ports), len(ports), False)
    else:
        res = json.load(open(a.out))
    print(json.dumps(report(res), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
