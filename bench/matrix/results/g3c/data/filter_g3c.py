#!/usr/bin/env python3
"""G3c data: filter sandbox runs (same rules as R2-C4 part 3), drop exact duplicates of the earlier public
corpora (T7, R2-C4 parts 1 to 3), then reject near-duplicates of every bench (36 cases, Steph Speak
Bench v1, bench v3 all lots) on command and output, then drop anything the PII scanner flags.
Public data only.

    python3 filter_g3c.py raw.jsonl public_g3c.jsonl filter_summary.json

Contamination rules (an example is dropped on any hit):
  - T7 rules: one long line (>= 24 chars) shared with the 36 cases or Speak Bench, or identical command;
  - v3 leak_check rules, per example: line Jaccard >= 0.5, 5-word shingle Jaccard >= 0.6, or same
    normalized command and line Jaccard >= 0.3, against every v3 case (raw output and production inputs);
  - stricter than v3: same normalized command and line Jaccard >= 0.15, or >= 3 normalized lines of
    >= 24 chars shared with one v3 case; v3 fingerprints.txt line hashes counted the same way;
  - v3 canary string anywhere.
"""
import collections, hashlib, json, os, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "bench/matrix/finetune"))
sys.path.insert(0, str(REPO / "bench/matrix/v3/tools"))
from compose_k3 import long_lines, bench_lines, speak_bench_lines  # noqa: E402
from audit_pii import scan_text, load_names  # noqa: E402
import leak_check as lc  # noqa: E402

NAMES = load_names(os.path.expanduser("~/.config/steph/pii_names.tsv"))
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]")
# uname and /proc expose the kernel of the host that ran the sandbox.
HOST_FINGERPRINT = re.compile(r"neofetch|pfetch|uname")
LEAK = re.compile(r"bwrap|setpriv|unshare|g3c|stephbench|steph-ft|rtx3060|backup-hdd|/srv/tpl|mut\.py|-pve\b|proxmox|total_system_memory", re.I)
MAX_EMPTY = 40
PRIOR = ["bench/matrix/results/finetune/loop/round-1/t7/public_t7.raw.jsonl",
         "bench/matrix/results/finetune/loop/round-2/r2c4-p1/public_p1.raw.jsonl",
         "bench/matrix/results/finetune/loop/round-2/r2c4-p2/public_p2.raw.jsonl",
         "bench/matrix/results/finetune/loop/round-2/r2c4-p3/data/public_p3.jsonl"]


def norm_out(o):
    return re.sub(r"\d", "0", o.strip())[:400]


def v3_cases():
    for p in sorted((REPO / "bench/matrix/v3/cases").glob("*.jsonl")):
        for l in open(p):
            if l.strip():
                yield json.loads(l)


def main(raw_path, out_path, summary_path):
    rows = [json.loads(l) for l in open(raw_path)]
    prior = set()
    for p in PRIOR:
        for l in open(REPO / p):
            if l.strip():
                d = json.loads(l)
                if d.get("output", "").strip():
                    prior.add(norm_out(ANSI.sub("", d["output"])))
    stats, kept, per_out, empty = collections.Counter(), [], collections.Counter(), 0
    for r in rows:
        r["output"] = ANSI.sub("", r["output"])
        o = r["output"]
        if HOST_FINGERPRINT.search(r["cmd"]):
            stats["host_fingerprint"] += 1; continue
        if r["exit"] in (124, 137) and "timeout" not in r["cmd"]:
            stats["timeout"] += 1; continue
        if LEAK.search(o):
            stats["sandbox_leak"] += 1; continue
        if not o.strip():
            if empty >= MAX_EMPTY:
                stats["empty_cap"] += 1; continue
            empty += 1
        if o.strip() and norm_out(o) in prior:
            stats["prior_corpus_duplicate"] += 1; continue
        key = (r["lang"], norm_out(o))
        if o.strip() and per_out[key] >= 2:
            stats["repeated_output_cap"] += 1; continue
        per_out[key] += 1
        kept.append(r)

    b_lines = bench_lines([REPO / "bench/matrix/cases.json"])
    s_lines = speak_bench_lines(REPO / "benchmark/data/v1")
    bench_cmds = {c["cmd"].strip() for c in json.load(open(REPO / "bench/matrix/cases.json"))}
    speak_cmds = set()
    for p in sorted((REPO / "benchmark/data/v1").glob("*/*.jsonl")):
        for l in p.read_text().splitlines():
            if l.strip():
                c = json.loads(l)
                if c.get("cmd"): speak_cmds.add(c["cmd"].strip())
                for h in c.get("history", []): speak_cmds.add(h.get("cmd", "").strip())

    cps = [lc.case_prints(c) for c in v3_cases()]
    index = collections.defaultdict(set)
    for k, cp in enumerate(cps):
        for rep in cp["reps"]:
            for h in rep["lines"]:
                index[h].add(k)
    fp_lines = {}
    for l in open(REPO / "bench/matrix/v3/fingerprints.txt"):
        if l.startswith("#") or "\t" not in l:
            continue
        cid, hs = l.rstrip("\n").split("\t")
        fp_lines[cid] = set(hs.split(","))
    fp_index = collections.defaultdict(set)
    for cid, hs in fp_lines.items():
        for h in hs:
            fp_index[h].add(cid)
    long_norm = lambda t: {hashlib.sha1(n.encode()).hexdigest()[:12] for n in lc.body_lines(t) if len(n) >= 24}

    cont, final, worst = collections.Counter(), [], []
    for r in kept:
        o, hit = r["output"], []
        ll = long_lines(o)
        if ll & b_lines: hit.append("bench36_line")
        if ll & s_lines: hit.append("speak_line")
        if r["cmd"].strip() in bench_cmds: hit.append("bench36_cmd")
        if r["cmd"].strip() in speak_cmds: hit.append("speak_cmd")
        if lc.CANARY in o: hit.append("canary")
        lines, sh = lc.fp(o)
        lng = long_norm(o)
        ncmd = lc.norm_cmd(r["cmd"])
        best = 0.0
        for k in set().union(*(index.get(h, set()) for h in lines)) if lines else set():
            cp = cps[k]
            for rep in cp["reps"]:
                rl, rs = set(rep["lines"]), set(rep["shingles"])
                j = lc.jac(lines, rl)
                best = max(best, j)
                if j >= 0.5: hit.append("v3_line")
                if lc.jac(sh, rs) >= 0.6: hit.append("v3_shingle")
                if ncmd in cp["cmds"] and j >= 0.15: hit.append("v3_same_cmd")
                if len(lng & rl) >= 3: hit.append("v3_3long")
        lfp = {hashlib.sha1(n.encode()).hexdigest()[:12] for n in (lc.norm_line(x) for x in o.split("\n")) if n}
        for cid in set().union(*(fp_index.get(h, set()) for h in lfp)) if lfp else set():
            j = lc.jac(lfp, fp_lines[cid])
            if j >= 0.3: hit.append("v3_fingerprints")
        if hit:
            for h in set(hit): cont[h] += 1
            cont["removed"] += 1
            continue
        texts = [v for v in r.values() if isinstance(v, str)]
        if scan_text("\n".join(texts), NAMES):
            cont["pii_dropped"] += 1; continue
        worst.append((best, r["cmd"][:60]))
        r["machine"] = "sandbox-debian13"
        r["source_license"] = r["source"]
        final.append(r)

    out = {"raw": len(rows), "stats_filter": dict(stats), "kept_before_contamination": len(kept),
           "contamination": dict(cont), "final": len(final),
           "final_by_lang": dict(collections.Counter(r["lang"] for r in final)),
           "final_by_family": dict(collections.Counter(r["family"] for r in final)),
           "final_distinct_cmds": len({r["cmd"] for r in final}),
           "final_exit_nonzero": sum(1 for r in final if r["exit"] != 0),
           "final_empty": sum(1 for r in final if not r["output"].strip()),
           "max_v3_line_jaccard_kept": max((b for b, _ in worst), default=0),
           "top_v3_line_jaccard_kept": sorted(worst, reverse=True)[:5],
           "v3_cases_checked": len(cps), "v3_fingerprint_cases": len(fp_lines)}
    with open(out_path, "w") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(out, open(summary_path, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
