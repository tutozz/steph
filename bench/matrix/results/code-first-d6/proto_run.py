import json, sys, collections, glob
sys.path.insert(0, '.')
exec(open(sys.argv[1]).read().split("def main():")[0])
exec(open(sys.argv[2]).read())
cases = score_v3.load_cases("dev"); h_ft = score_v3.load_harness("dev")
h_gen = {h["id"]: h for h in json.load(open(sys.argv[3]))}
S = sys.argv[4]; show = len(sys.argv) > 5
M_ = {"v10": [sp.score_run(cases, f"{S}/runs/v10-dev-b{sd}.json", h_ft)["per_case"] for sd in (7, 42, 123)],
      "gemmaL5": [sp.score_run(cases, f"../../results/aids-input/runs/gemma-facts-dev-b{sd}.json", h_gen)["per_case"] for sd in (7, 42, 123)]}
if glob.glob(f"{S}/runs/g3b-dev-b*.json"):
    M_["g3b"] = [sp.score_run(cases, p, h_gen)["per_case"] for p in sorted(glob.glob(f"{S}/runs/g3b-dev-b*.json"))]
first = M_["v10"][0]; N = len(first)
res = collections.defaultdict(lambda: {"rows": 0, "code": 0.0, "d": collections.Counter(), "h": collections.Counter(), "up": collections.Counter(), "down": collections.Counter()})
lots = collections.defaultdict(lambda: {"rows": 0, "d": collections.Counter(), "h": collections.Counter()})
for rid in first:
    cid, lang = score_v3.parse_row_id(rid); c = cases[cid]
    if c["task"] == "qa" or first[rid]["source"] == "code": continue
    out = "\n".join(v3lib.output_lines(c["output_raw"])); w = words(c["cmd"])
    for lot, bs in BUILDERS.items():
        said = next(((b.__name__, s) for b in bs if (s := b(c["cmd"], c["exit"], out, w))), None)
        if said: break
    if not said: continue
    name, (fr, en) = said
    text = sp.status_prefix(c, lang) + (fr if lang == "fr" else en)
    sc = score_v3.score_answer(c, lang, text)
    r = res[(lot, name)]; r["rows"] += 1; r["code"] += sc; lots[lot]["rows"] += 1
    for m, runs in M_.items():
        ms = sum(run[rid]["score"] for run in runs) / len(runs)
        pre = sp.status_prefix(c, lang)
        hy = sum(score_v3.score_answer(c, lang, pre + (fr if lang == "fr" else en) + " " + run[rid]["said"][len(pre):] if run[rid]["said"].startswith(pre) else run[rid]["said"]) for run in runs) / len(runs)
        r["h"][m] += hy - ms; lots[lot]["h"][m] += hy - ms
        r["d"][m] += sc - ms; lots[lot]["d"][m] += sc - ms
        r["up"][m] += sc > ms + 1e-9; r["down"][m] += sc < ms - 1e-9
    if show: print(f"{rid:34} {sc:.2f} | {text}")
for (lot, name), r in sorted(res.items()):
    print(lot, name, r["rows"], f"code {r['code']/r['rows']:.2f}", " ".join(f"{m}: {100*r['d'][m]/N:+.2f} ({r['up'][m]}+/{r['down'][m]}-) hyb {100*r['h'][m]/N:+.2f}" for m in M_))
tot = collections.Counter(); rows = 0
for lot, L in sorted(lots.items()):
    rows += L["rows"]; tot.update(L["d"])
    print("LOT", lot, L["rows"], " ".join(f"{m}: {100*L['d'][m]/N:+.2f} hyb {100*L['h'][m]/N:+.2f}" for m in M_))
code_now = sum(1 for rid in first if first[rid]["source"] == "code")
print("ALL", rows, " ".join(f"{m}: {100*tot[m]/N:+.2f}" for m in M_), "share", round(100*code_now/N, 1), "->", round(100*(code_now+rows)/N, 1))
