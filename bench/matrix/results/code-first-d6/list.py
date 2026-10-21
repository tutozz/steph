import json, sys, collections
sys.argv_saved = sys.argv[:]
sys.path.insert(0, '.')
exec(open(sys.argv[1]).read().split("def main():")[0])
cases = score_v3.load_cases("dev"); h_ft = score_v3.load_harness("dev")
h_gen = {h["id"]: h for h in json.load(open(sys.argv[2]))}
S = sys.argv[3]
v = [sp.score_run(cases, f"{S}/runs/v10-dev-b{sd}.json", h_ft)["per_case"] for sd in (7, 42, 123)]
g = [sp.score_run(cases, f"../../results/aids-input/runs/gemma-facts-dev-b{sd}.json", h_gen)["per_case"] for sd in (7, 42, 123)]
by = collections.defaultdict(list)
for rid in v[0]:
    cid, lang = score_v3.parse_row_id(rid); c = cases[cid]
    if c["task"] == "qa" or lang != "fr": continue
    ide = cid + "@en"
    src = v[0][rid]["source"]
    sv = sum(r[rid]["score"] + r[ide]["score"] for r in v) / 6; sg = sum(r[rid]["score"] + r[ide]["score"] for r in g) / 6
    by[fam(c["cmd"])].append((src, cid, c["cmd"][:70], c["exit"], c["nlines"], round(sv, 2), round(sg, 2), c["reference"]["en"][:110] if isinstance(c["reference"], dict) else str(c["reference"])[:110]))
for f, L in sorted(by.items()):
    print("=====", f)
    for x in sorted(L): print(" ", *x, sep=" | ")
