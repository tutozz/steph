import json, sys, collections
sys.path.insert(0, '.')
exec(open(sys.argv[1]).read().split("def main():")[0])
exec(open(sys.argv[2]).read())
cases = score_v3.load_cases("dev"); h_ft = score_v3.load_harness("dev")
h_gen = {h["id"]: h for h in json.load(open(sys.argv[3]))}
S = sys.argv[4]
M_ = {"v10": [sp.score_run(cases, f"{S}/runs/v10-dev-b{sd}.json", h_ft)["per_case"] for sd in (7, 42, 123)],
      "gemmaL5": [sp.score_run(cases, f"../../results/aids-input/runs/gemma-facts-dev-b{sd}.json", h_gen)["per_case"] for sd in (7, 42, 123)]}
import glob
if glob.glob(f"{S}/runs/g3b-dev-b*.json"):
    M_["g3b"] = [sp.score_run(cases, p, h_gen)["per_case"] for p in sorted(glob.glob(f"{S}/runs/g3b-dev-b*.json"))]
first = M_["v10"][0]; N = len(first)
per_rule = collections.defaultdict(lambda: {"rows": 0, "cases": set(), "ms": collections.Counter()})
per_lot = collections.defaultdict(lambda: {"rows": 0, "ms": collections.Counter(), "fams": set()})
covered = set()
for rid in first:
    cid, lang = score_v3.parse_row_id(rid); c = cases[cid]
    if c["task"] == "qa" or first[rid]["source"] == "code": continue
    out = "\n".join(v3lib.output_lines(c["output_raw"])); w = words(c["cmd"])
    hit = next(((lot, f, name) for lot, f, name, fn in RULES if fn(c["cmd"], c["exit"], out, w)), None)
    if not hit: continue
    covered.add(rid)
    lot, f, name = hit
    r = per_rule[(lot, f, name)]; r["rows"] += 1; r["cases"].add(cid)
    L = per_lot[lot]; L["rows"] += 1; L["fams"].add(fam(c["cmd"]))
    for m, runs in M_.items():
        s = sum(run[rid]["score"] for run in runs) / len(runs)
        r["ms"][m] += s; L["ms"][m] += s
def gain(rows, ssum, E): return round(100 * (E * rows - ssum) / N, 2)
print("N", N, "models", list(M_))
for (lot, f, name), r in sorted(per_rule.items()):
    print(lot, f, "|", name, "|", r["rows"], "|", " ".join(f"{m}: moy {r['ms'][m]/r['rows']:.2f} g78 {gain(r['rows'], r['ms'][m], .78):+.2f} g60 {gain(r['rows'], r['ms'][m], .60):+.2f}" for m in M_))
tot = collections.Counter(); rows = 0
for lot, L in sorted(per_lot.items()):
    rows += L["rows"]
    print("LOT", lot, L["rows"], sorted(L["fams"]), " ".join(f"{m}: g78 {gain(L['rows'], L['ms'][m], .78):+.2f} g60 {gain(L['rows'], L['ms'][m], .60):+.2f}" for m in M_))
code_now = sum(1 for rid in first if first[rid]["source"] == "code")
print("code share", round(100 * code_now / N, 1), "->", round(100 * (code_now + rows) / N, 1), "covered rows", rows)
json.dump(sorted(covered), open(f"{S}/covered.json", "w"))
