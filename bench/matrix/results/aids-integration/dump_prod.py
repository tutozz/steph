"""Usage: dump_prod.py <split> <harness_or_-> <out.json> <runs...> ; run from <root>/bench/matrix/v3/tools."""
import json, sys
sys.path.insert(0, ".")
import score_v3, score_production
split, hp, out, runs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
cases = score_v3.load_cases(split)
harness = score_v3.load_harness(split) if hp == "-" else {h["id"]: h for h in json.load(open(hp))}
res = {}
for p in runs:
    r = score_production.score_run(cases, p, harness, True)
    res[p.split("/")[-1]] = r
    print(p.split("/")[-1], r["quality"], r["code_share"], r["code_quality"], r["model_quality"])
json.dump(res, open(out, "w"), ensure_ascii=False)
