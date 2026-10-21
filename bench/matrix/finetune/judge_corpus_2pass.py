"""Judge teacher labels of the fine-tuning corpus for invented facts, 2-pass consensus.

    python3 judge_corpus_2pass.py labels.jsonl machine_name out_dir

Same method as A7 (docs/judge-a7.md) and run_fixed.py: pass A and pass B per row, "invention"
only when both agree, "douteux" when only one flags it, "ok" otherwise. A11 filtered the
corpus with a single pass (judge_corpus.py); K2 asks for the stricter 2-pass method here.

Verdicts are appended to out_dir/verdicts-<machine>.jsonl (resumable, stays on this machine);
at the end out_dir/rejects-<machine>.txt holds only the sha256 of rejected (invention) user
messages, matching the format of A11's judge-rejects.txt, and out_dir/rejects-<machine>.counts.json
the summary by category. `douteux` rows are kept (not written to rejects), like A7/A11.

SPDX-License-Identifier: MIT
"""

import collections
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge_lib import call_judge  # noqa: E402

STATUS = re.compile(r"succ[èe]s|[ée]chec|r[ée]ussi|statut|code de sortie|success|fail(?:ed|ure)?|status|exit code", re.I)
NAME = re.compile(r"[\w-]+[./_][\w./-]+|\b[a-z0-9]+-[a-z0-9-]+\b", re.I)


def digest(row):
    return hashlib.sha256(row["messages"][1]["content"].encode()).hexdigest()


def category(fact):
    if re.search(r"\bligne\b|\bline\b", fact, re.I):
        return "ligne"
    if STATUS.search(fact):
        return "statut"
    if re.search(r"\d", fact):
        return "nombre"
    if NAME.search(fact):
        return "nom"
    return "cause"


def judge_pass(ctx, phrase, pass_id, retries=2):
    res = None
    for _ in range(retries + 1):
        try:
            res = call_judge(ctx, phrase, pass_id=pass_id, timeout=300)
        except Exception as e:
            res = {"verdict": "erreur", "inventions": [], "_error": str(e)}
        if res["verdict"] in ("ok", "invention"):
            return res
        time.sleep(2)
    return res


def consensus(va: str, vb: str) -> str:
    """2-pass rule of A7/run_fixed.py : invention only on agreement, douteux on split,
    erreur only when nothing usable came back from either pass."""
    if va == "invention" and vb == "invention":
        return "invention"
    if va == "invention" or vb == "invention":
        return "douteux"
    if va == "erreur" or vb == "erreur":
        return "erreur"
    return "ok"


def judge(row):
    ctx, phrase = row["messages"][1]["content"], row["messages"][2]["content"]
    res_a = judge_pass(ctx, phrase, "A")
    res_b = judge_pass(ctx, phrase, "B")
    va, vb = res_a["verdict"], res_b["verdict"]
    final = consensus(va, vb)
    inventions = list({str(f) for f in res_a.get("inventions", []) + res_b.get("inventions", [])})
    return {"verdict": final, "pass_A": va, "pass_B": vb, "inventions": inventions}


def main(src, machine, out_dir):
    rows = [json.loads(line) for line in open(src) if line.strip()]
    mine = {}
    for r in rows:
        mine.setdefault(digest(r), r)
    verdict_path = os.path.join(out_dir, f"verdicts-{machine}.jsonl")
    done = {}
    if os.path.exists(verdict_path):
        for line in open(verdict_path):
            v = json.loads(line)
            if v["verdict"] in ("ok", "invention", "douteux"):
                done[v["sha"]] = v
    todo = [(h, r) for h, r in mine.items() if h not in done]
    print(f"{len(mine)} étiquettes à juger (2 passes), {len(done)} déjà faites, {len(todo)} restantes", flush=True)
    t0 = time.time()
    with open(verdict_path, "a") as out, ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(judge, r): h for h, r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            h = futs[fut]
            res = fut.result()
            v = {"sha": h, **res}
            out.write(json.dumps(v, ensure_ascii=False) + "\n")
            out.flush()
            done[h] = v
            if i % 50 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)

    verdicts = collections.Counter(v["verdict"] for h, v in done.items() if h in mine)
    rejects = sorted(h for h, v in done.items() if h in mine and v["verdict"] == "invention")
    cats = collections.Counter()
    for h in rejects:
        for c in {category(str(f)) for f in done[h]["inventions"]} or {"non précisée"}:
            cats[c] += 1
    with open(os.path.join(out_dir, f"rejects-{machine}.txt"), "w") as f:
        f.writelines(h + "\n" for h in rejects)
    summary = {"machine": machine, "judged": len(mine), "verdicts": dict(verdicts),
               "rejected": len(rejects), "categories": dict(cats)}
    with open(os.path.join(out_dir, f"rejects-{machine}.counts.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
