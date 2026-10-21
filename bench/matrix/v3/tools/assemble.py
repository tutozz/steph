#!/usr/bin/env python3
"""Assembles the bench v3 from the lot files (cases/L*.jsonl): checks, drops, splits, harness.

    python3 assemble.py --leak rtx3080.json a1000.json local.json

Lots stay the source of truth: fix a case in its lot, then rerun. Steps:
1. validate.py on every case (schema, production input at HEAD, reference at 100 %); any error aborts.
2. Drops: final leak control (leak_check.py results, any corpus rejected), internal duplicates
   (v3-fp1 line Jaccard >= 0.7 between two summaries; qa on the same session with another
   question is kept), and the hand-listed DROPS below.
3. Split: the lot split is kept (stratified by family, capture kept together); checked here:
   case_ref in the same split, dev share per family between 30 and 50 %.
4. Writes cases/<split>/<family>.jsonl, harness/<split>.json (bench_run.py format, one row per
   case and prompt language, id `<case>@<fr|en>`), fingerprints.txt and assembly.json.

SPDX-License-Identifier: MIT
"""

import argparse
import itertools
import json
from collections import Counter, defaultdict

import v3lib
import validate

DROPS = {}

TARGETS = {
    "vcs-git": 40, "tests": 40, "files": 40, "build-native": 30, "js-node": 30, "python": 30,
    "containers": 30, "packages-system": 30, "services-logs": 30, "network": 30, "disk-memory": 25,
    "network-transfer": 25, "rust-go": 20, "lint-format": 20, "processes": 20, "data": 20,
    "hardware-system": 15, "shell-scripts": 15, "permissions-users": 12, "infra": 8, "history-qa": 90,
}
SHARE_TARGETS = {
    "os": {"linux": 0.60, "macos": 0.40},
    "output_lang": {"fr": 0.25, "en": 0.65, "none": 0.10},
    "status": {"failure": 0.50, "success": 0.50},
    "length_class": {"short": 0.30, "medium": 0.35, "long": 0.35},
    "difficulty": {"easy": 0.25, "medium": 0.45, "hard": 0.30},
    "origin": {"real": 0.80, "reconstructed": 0.20},
}


def load_lots():
    cases = []
    for p in sorted((v3lib.V3 / "cases").glob("L*.jsonl")):
        cases += [json.loads(l) for l in open(p) if l.strip()]
    return cases


def leak_drops(paths):
    worst = {}
    for p in paths:
        r = json.load(open(p))
        for c in r["cases"]:
            w = worst.setdefault(c["id"], {"line": 0.0, "shingle": 0.0, "same_cmd_line": 0.0, "rejected": False, "by": []})
            for k in ("line", "shingle", "same_cmd_line"):
                w[k] = max(w[k], c[k])
            if c["rejected"]:
                w["rejected"] = True
                w["by"].append(p.rsplit("/", 1)[-1].removesuffix(".json"))
    return worst


def internal_duplicates(cases):
    fps = {c["id"]: v3lib.line_fps(v3lib.case_text(c)) for c in cases}
    drops = {}
    for a, b in itertools.combinations([c for c in cases if c["task"] == "summary"], 2):
        if a["id"] in drops or b["id"] in drops:
            continue
        j = v3lib.jaccard(fps[a["id"]], fps[b["id"]])
        if j >= 0.7:
            drops[b["id"]] = f"doublon interne de {a['id']} (Jaccard de lignes {j:.2f})"
    return drops


def shares(cases, key):
    n = Counter(c.get(key) for c in cases)
    tot = sum(n.values())
    return {k: {"n": v, "share": round(v / tot, 3)} for k, v in sorted(n.items(), key=lambda kv: str(kv[0]))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leak", nargs="+", required=True, help="leak_check.py scan/local results")
    a = ap.parse_args()
    cases = load_lots()
    errors = {c["id"]: e for c in cases if (e := validate.case_errors(c))}
    if errors:
        print(json.dumps(errors, ensure_ascii=False, indent=1))
        raise SystemExit(1)
    leak = leak_drops(a.leak)
    missing = [c["id"] for c in cases if c["id"] not in leak]
    if missing:
        raise SystemExit(f"leak results miss {len(missing)} cases, e.g. {missing[:3]}")
    dropped = dict(DROPS)
    for cid, w in leak.items():
        if w["rejected"]:
            dropped[cid] = (f"fuite v3-fp1 ({', '.join(w['by'])}) : Jaccard de lignes {w['line']}, "
                            f"shingles {w['shingle']}, même commande {w['same_cmd_line']}")
    dropped.update({k: v for k, v in internal_duplicates(cases).items() if k not in dropped})
    kept = [c for c in cases if c["id"] not in dropped]

    for c in kept:
        w = leak[c["id"]]
        c["leak_check"] = {"method": "v3-fp1", "corpora": ["rtx3080-final", "a1000-k3-mix", "speak-bench-v1", "bench-v2", "rtx3080-r1-k3-r2c2", "xeon-final", "a1000-r1-k3", "r2c4-rtx3060", "r2c4-repo", "t7-public"],
                           "max_line_jaccard": w["line"], "max_shingle_jaccard": w["shingle"],
                           "same_command_hit": w["same_cmd_line"] > 0, "passed": True}
        assert not validate.case_errors(c), c["id"]

    ids = {c["id"]: c for c in kept}
    ref_errors = [(c["id"], h["case_ref"]) for c in kept if c["task"] == "qa" for h in c["history"]
                  if h.get("case_ref") and (h["case_ref"] not in ids or ids[h["case_ref"]]["split"] != c["split"])]
    per_family = defaultdict(Counter)
    for c in kept:
        per_family[c["family"]][c["split"]] += 1
    dev_share = {f: round(v["dev"] / (v["dev"] + v["test"]), 2) for f, v in sorted(per_family.items())}
    off = {f: s for f, s in dev_share.items() if not 0.30 <= s <= 0.50}
    if ref_errors or off:
        raise SystemExit(f"split check failed: case_ref {ref_errors}, dev share {off}")

    out_cases = v3lib.V3 / "cases"
    for split in ("dev", "test"):
        d = out_cases / split
        d.mkdir(exist_ok=True)
        for old in d.glob("*.jsonl"):
            old.unlink()
        by_family = defaultdict(list)
        for c in sorted((c for c in kept if c["split"] == split), key=lambda c: c["id"]):
            by_family[c["family"]].append(c)
        for fam, cs in by_family.items():
            with open(d / f"{fam}.jsonl", "w") as f:
                for c in cs:
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")
        rows = []
        for c in sorted((c for c in kept if c["split"] == split), key=lambda c: c["id"]):
            for lang in ("fr", "en"):
                rows.append({"id": f"{c['id']}@{lang}", "fixture": c["id"],
                             "cmd": c["cmd"] if c["task"] == "summary" else c["question"][lang],
                             "kind": c["task"], "maxc": 0, "messages": c["input"][lang], "lang": lang,
                             "family": c["family"], "reaches_model": v3lib.reaches_model(c, lang),
                             "payload": v3lib.production_payload(c["task"])})
        (v3lib.V3 / "harness").mkdir(exist_ok=True)
        json.dump(rows, open(v3lib.V3 / "harness" / f"{split}.json", "w"), ensure_ascii=False, indent=0)

    with open(v3lib.V3 / "fingerprints.txt", "w") as f:
        f.write("# STEPH BENCH V3 - NEVER TRAIN ON THIS. steph-bench-v3-canary-6e21d5e02bf0\n")
        f.write("# v3-fp1 line fingerprints (sha1[:12] of normalized lines, tools/v3lib.py), one case per line\n")
        for c in sorted(kept, key=lambda c: c["id"]):
            f.write(c["id"] + "\t" + ",".join(sorted(v3lib.line_fps(v3lib.case_text(c)))) + "\n")

    summaries = [c for c in kept if c["task"] == "summary"]
    reach = Counter((lang, v3lib.reaches_model(c, lang)) for c in summaries for lang in ("fr", "en"))
    report = {
        "lots": len(cases), "kept": len(kept), "dropped": dropped,
        "splits": dict(Counter(c["split"] for c in kept)),
        "evaluations": {"all": 2 * len(kept), "dev": 2 * sum(c["split"] == "dev" for c in kept),
                        "test": 2 * sum(c["split"] == "test" for c in kept)},
        "families": {f: {"n": sum(per_family[f].values()), "target": TARGETS[f],
                         "gap": sum(per_family[f].values()) - TARGETS[f], **per_family[f]} for f in TARGETS},
        "dev_share_by_family": dev_share,
        "shares_summary": {k: {"observed": shares(summaries, k), "target": t} for k, t in SHARE_TARGETS.items()},
        "qa": {"n": len(kept) - len(summaries),
               "answer_in_history": dict(Counter(str(c["answer_in_history"]) for c in kept if c["task"] == "qa")),
               "by_split": dict(Counter(c["split"] for c in kept if c["task"] == "qa"))},
        "os_all": shares(kept, "os"),
        "contested": [c["id"] for c in kept if c.get("review", {}).get("contested")],
        "summary_reaches_model": {f"{lang}_{ok}": n for (lang, ok), n in sorted(reach.items())},
        "second_reader": dict(Counter(bool(c.get("review", {}).get("second_reader")) for c in kept)),
    }
    json.dump(report, open(v3lib.V3 / "assembly.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("lots", "kept", "splits", "evaluations", "dropped")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
