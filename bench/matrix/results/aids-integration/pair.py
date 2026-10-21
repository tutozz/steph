"""Usage: pair.py <split> <before_tag> <after_tag>; run from bench/matrix/v3/tools."""
import json, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, ".")
import power_v3, score_v3
S = sys.argv[4] if len(sys.argv) > 4 else "."
split, bt, at = sys.argv[1:4]
all_cases = score_v3.load_cases("all")
sizes = {split: sum(c["split"] == split for c in all_cases.values())}
report = {}
for m in ("r1", "gemma"):
    b, a = json.load(open(f"{S}/{split}-{m}-{bt}.json")), json.load(open(f"{S}/{split}-{m}-{at}.json"))
    def per(d):
        out = defaultdict(list)
        for f in sorted(d):
            for rid, p in d[f]["per_case"].items():
                out[rid].append(p["score"])
        return out
    pa, pb = per(a), per(b)
    rng = np.random.default_rng(20260928)
    r = power_v3.compare(power_v3.case_means(pa), power_v3.case_means(pb), sizes, rng, 100)
    changed = better = worse = 0
    for f in b:
        for rid, p in b[f]["per_case"].items():
            q = a[f]["per_case"][rid]
            if q["said"] != p["said"]:
                changed += 1
                better += q["score"] > p["score"] + 1e-9
                worse += q["score"] < p["score"] - 1e-9
    r.update(changed_evals=changed, better=better, worse=worse,
             seeds_before=[b[f]["quality"] for f in sorted(b)], seeds_after=[a[f]["quality"] for f in sorted(a)],
             code_share_after=[a[f]["code_share"] for f in sorted(a)][0])
    report[m] = r
    print(m, json.dumps({k: r[k] for k in ("n_cases", "a", "b", "diff", "ci95", "sign_test_p", "discordant_cases", "changed_evals", "better", "worse", "seeds_before", "seeds_after", "code_share_after")}, ensure_ascii=False))
json.dump(report, open(f"{S}/pair-{split}-{bt}-{at}.json", "w"), indent=1)
