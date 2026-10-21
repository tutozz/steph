"""r3t5_judge.py <harness.json> <cache.json> <out.json> <run.json> [...] --urls <url> [...] [--threads 8]

A7 invention judge over bench v3 runs, with the round-3 speed rules:
- only answers steph sends to the model (harness `reaches_model`), the others are said in code;
- one verdict per (context, answer) fingerprint, cached and shared across models and seeds;
- the unjudged fingerprints are split across every judge server given, each with its own pool.
Verdict rule and retries are those of bench/matrix/v3/tools/judge_v3.py; the A7 judge_lib is
loaded untouched, once per server. <out.json> uses the judge_v3 row format (power_v3 --judge).

SPDX-License-Identifier: MIT
"""
import argparse
import hashlib
import importlib.util
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
A7 = os.path.join(HERE, "..", "judge_lib_a7.py")


def load_judge(url):
    spec = importlib.util.spec_from_file_location(f"a7_{hashlib.md5(url.encode()).hexdigest()}", A7)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.URL = url
    return mod.call_judge


def retry(call, ctx, phrase, pass_id):
    last = None
    for _ in range(3):
        try:
            r = call(ctx, phrase, pass_id=pass_id)
        except Exception as e:
            r = {"inventions": [], "verdict": "erreur", "_error": str(e)[:200]}
        if r["verdict"] in ("ok", "invention"):
            return r
        last = r
        time.sleep(1)
    return last


def final_verdict(va, vb):
    if va == vb == "invention":
        return "invention"
    if "invention" in (va, vb):
        return "douteux"
    return "erreur" if "erreur" in (va, vb) else "ok"


def judge_context(messages):
    return "\n\n".join(m["content"] for m in messages if m["role"] == "user")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("harness")
    ap.add_argument("cache")
    ap.add_argument("out")
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--urls", nargs="+", required=True)
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    harness = {c["id"]: c for c in json.load(open(a.harness))}
    cache = json.load(open(a.cache)) if os.path.exists(a.cache) else {}
    cache = {k: v for k, v in cache.items() if v["final"] != "erreur"}
    rows, todo = [], {}
    for f in a.runs:
        for r in json.load(open(f))["rows"]:
            case = harness[r["id"]]
            if not case.get("reaches_model") or not (r.get("out") or "").strip():
                continue
            ctx = judge_context(case["messages"])
            key = hashlib.sha256(f"{ctx}\x00{r['out']}".encode()).hexdigest()
            rows.append((os.path.basename(f), r["id"], r["out"], key))
            if key not in cache:
                todo[key] = (ctx, r["out"])
    print(f"{len(rows)} answers, {len(set(k for *_, k in rows))} distinct, {len(todo)} to judge on {len(a.urls)} servers", flush=True)
    lock, done = threading.Lock(), [0]

    def work(call, key):
        ctx, phrase = todo[key]
        va, vb = retry(call, ctx, phrase, "A"), retry(call, ctx, phrase, "B")
        with lock:
            cache[key] = {"pass_A": {"verdict": va["verdict"], "inventions": va["inventions"]},
                          "pass_B": {"verdict": vb["verdict"], "inventions": vb["inventions"]},
                          "final": final_verdict(va["verdict"], vb["verdict"])}
            done[0] += 1
            if done[0] % 50 == 0 or done[0] == len(todo):
                json.dump(cache, open(a.cache, "w"), ensure_ascii=False)
                print(f"{done[0]}/{len(todo)}", flush=True)

    keys = sorted(todo)
    pools = []
    for i, url in enumerate(a.urls):
        call = load_judge(url)
        ex = ThreadPoolExecutor(a.threads)
        for k in keys[i::len(a.urls)]:
            ex.submit(work, call, k)
        pools.append(ex)
    for ex in pools:
        ex.shutdown(wait=True)
    json.dump(cache, open(a.cache, "w"), ensure_ascii=False)
    out = [{"model_file": m, "id": rid, "phrase": phrase, **cache[k]} for m, rid, phrase, k in rows if k in cache]
    json.dump(out, open(a.out, "w"), ensure_ascii=False)
    summary = {}
    for m, *_ in rows:
        summary.setdefault(m, None)
    for m in summary:
        rs = [r for r in out if r["model_file"] == m]
        summary[m] = {k: sum(r["final"] == k for r in rs) for k in ("invention", "douteux", "erreur", "ok")}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
