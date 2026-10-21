"""T4 : étalonnage du proxy xeon contre les TTFT i5 connus, puis tableau prédit."""
import json, glob, os, statistics as st, sys, math
R = sys.argv[1]            # dossier res/ rapatrié
REPO = sys.argv[2]         # racine du dépôt
F = f"{REPO}/bench/matrix/results/finetune"

def p90(xs):
    xs = sorted(xs); k = 0.9 * (len(xs) - 1); f = math.floor(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)

def load(label):
    p = f"{R}/{label}.json"
    if not os.path.exists(p): return None
    d = json.load(open(p)); rows = [r for r in d["rows"] if r.get("ttft") is not None]
    if len(rows) < len(d["rows"]): return None
    t = [r["ttft"] for r in rows]
    return {"p50": st.median(t), "p90": p90(t), "prompt_n": sum(r.get("prompt_n", 0) for r in rows),
            "gen": d.get("gen_tok_s_median"), "ram": d.get("ram_peak_mb"), "n": len(rows)}

def i5(files):
    v = [json.load(open(f"{F}/{f}"))["ttft_p90"] for f in files]
    return st.median(v)

# i5 : mêmes cas (cases_ft36, maxc 1500), -t 4 -c 4096 -ub 512, llama-server b11205
CAL = {
 "gemma3-270m-base-Q4_0":  (["i5-opt/i5-opt-gemma-Q40-t4ub512.json"], 10269),
 "gemma3-270m-base-Q8_0":  (["i5-judged-gemma-270m-s42-Q8_0.json", "i5-gemma3-270m-ft500-Q8_0.json", "i5-gemma3-270m-ftfull-Q8_0.json"], 10269),
 "gemma3-270m-base-Q4_K_M": (["i5-opt/i5-opt-gemma-Q4KM-t4ub512.json"], 10269),
 "granite-4.0-h-350m-Q4_0": (["i5-opt/i5-opt-granite-Q40-t4ub512.json"], 6178),
 "granite-4.0-h-350m-Q4_K_M": ([f"vocab/i5-vocab-granite-full-Q4_K_M-p{i:02d}.json" for i in (1,3,5,8,10,12)], 6178),
 "granite-4.0-h-350m-Q8_0": (["i5-a1000-granite4.0-h-350m-ft-Q8_0.json"], 6178),
 "qwen3-0.6b-Q4_K_M":      (["i5-luth-0.6b-ft-r16-Q4_K_M.json"], 6527),
 "qwen3.5-0.8b-Q4_K_M":    (["i5-qwen3.5-0.8b-full-Q4_K_M.json"], 6965),
 "qwen3.5-0.8b-Q8_0":      (["i5-qwen3.5-0.8b-full-Q8_0.json"], 6965),
}
EXACT = {"exact-gemma-ft500-Q8_0": ["i5-gemma3-270m-ft500-Q8_0.json"],
         "exact-granite-soup-Q4_K_M": [f"vocab/i5-vocab-granite-full-Q4_K_M-p{i:02d}.json" for i in (1,3,5,8,10,12)]}

def rank(v):
    s = sorted(range(len(v)), key=lambda i: v[i]); r = [0]*len(v); i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and v[s[j+1]] == v[s[i]]: j += 1
        for k in range(i, j+1): r[s[k]] = (i + j) / 2
        i = j + 1
    return r

def pearson(x, y):
    mx, my = st.mean(x), st.mean(y)
    return sum((a-mx)*(b-my) for a, b in zip(x, y)) / math.sqrt(sum((a-mx)**2 for a in x) * sum((b-my)**2 for b in y))

def spearman(x, y): return pearson(rank(x), rank(y))

def fit(x, y):
    mx, my = st.mean(x), st.mean(y)
    a = sum((p-mx)*(q-my) for p, q in zip(x, y)) / sum((p-mx)**2 for p in x)
    return a, my - a*mx

out = {"calibration": {}, "proxies": {}}
names = list(CAL)
y = [i5(CAL[n][0]) for n in names]
for n, yy in zip(names, y): out["calibration"][n] = {"i5_p90": round(yy, 3), "i5_prompt_n": CAL[n][1]}

def lb(n, key):
    p = f"{R}/lb-hsw4-{n}.json"
    if not os.path.exists(p): return None
    for r in json.load(open(p)):
        if r["n_prompt"] == key[0] and r["n_gen"] == key[1]: return r["avg_ts"]

for proxy in ("hsw4-ft36", "nat4-ft36", "nat32-ft36", "lb-pp512", "lb-pp512-scaled"):
    x = []
    for n in names:
        if proxy.startswith("lb"):
            ts = lb(n, (512, 0)); pn = CAL[n][1]
            x.append(None if ts is None else (1/ts if proxy == "lb-pp512" else pn/ts))
        else:
            vals = [load(f"{proxy}-{n}-p{p}") for p in (1, 2)]
            vals = [v for v in vals if v]
            x.append(st.median([v["p90"] for v in vals]) if vals else None)
            for v in vals:
                out["calibration"][n].setdefault(proxy + "_prompt_n", v["prompt_n"])
    ok = [i for i, v in enumerate(x) if v is not None]
    if len(ok) < 4: continue
    xs, ys = [x[i] for i in ok], [y[i] for i in ok]
    a, b = fit(xs, ys)
    loo = []
    for k in range(len(xs)):
        a2, b2 = fit(xs[:k]+xs[k+1:], ys[:k]+ys[k+1:])
        loo.append(abs(a2*xs[k]+b2 - ys[k]) / ys[k])
    out["proxies"][proxy] = {"n": len(xs), "spearman": round(spearman(xs, ys), 3), "pearson": round(pearson(xs, ys), 3),
                             "fit_a": round(a, 4), "fit_b": round(b, 4), "loo_mape_pct": round(100*st.mean(loo), 1),
                             "loo_max_pct": round(100*max(loo), 1),
                             "points": {names[i]: round(x[i], 4) for i in ok}}
# exacts : même fichier GGUF que celui mesuré sur l'i5
out["exact"] = {}
for n, fs in EXACT.items():
    v = [load(f"hsw4-ft36-{n}-p{p}") for p in (1, 2)]; v = [q for q in v if q]
    out["exact"][n] = {"i5_p90": i5(fs), "hsw4_p90": [round(q["p90"], 3) for q in v], "prompt_n": [q["prompt_n"] for q in v]}
# tableau prédit sur le format B3 (36 cas compact)
a, b = out["proxies"]["hsw4-ft36"]["fit_a"], out["proxies"]["hsw4-ft36"]["fit_b"]
table = {}
for p in sorted(glob.glob(f"{R}/hsw4-b3-*-p1.json")):
    n = os.path.basename(p)[len("hsw4-b3-"):-len("-p1.json")]
    vals = [v for v in (load(f"hsw4-b3-{n}-p{k}") for k in (1, 2)) if v]
    ft = [v for v in (load(f"hsw4-ft36-{n}-p{k}") for k in (1, 2)) if v]
    tag = n.rsplit("-Q", 1)[0]
    tk = f"{R}/tok-{tag}.json"
    tok = json.load(open(tk)) if os.path.exists(tk) else None
    size = os.path.getsize(f"{R}/../q/{n}.gguf") if os.path.exists(f"{R}/../q/{n}.gguf") else None
    p90b3 = st.median([v["p90"] for v in vals]); p50b3 = st.median([v["p50"] for v in vals])
    row = {"hsw4_b3_p50": round(p50b3, 3), "hsw4_b3_p90": round(p90b3, 3),
           "pred_i5_b3_p90": round(a*p90b3 + b, 2), "pred_i5_b3_p50": round(a*p50b3 + b, 2),
           "hsw4_ft36_p90": round(st.median([v["p90"] for v in ft]), 3) if ft else None,
           "pred_i5_ft36_p90": round(a*st.median([v["p90"] for v in ft]) + b, 2) if ft else None,
           "b3_prompt_n": vals[0]["prompt_n"], "gen_tok_s_hsw4": vals[0]["gen"], "ram_peak_mb_hsw4": vals[0]["ram"],
           "passes": len(vals)}
    if tok:
        row.update({"tok_b3_user_mean": round(st.mean(tok["bench36_user"]), 1), "tok_b3_user_p90": round(p90(tok["bench36_user"]), 1),
                    "tok_sys_fr": tok["sys_fr"][0], "tok_sys_en": tok["sys_en"][0],
                    "tok_ssb_fr_mean": round(st.mean(tok["ssb_fr_user"]), 1), "tok_ssb_en_mean": round(st.mean(tok["ssb_en_user"]), 1),
                    "fr_over_en": round(sum(tok["ssb_fr_user"]) / sum(tok["ssb_en_user"]), 3),
                    "chars_per_tok_fr": round(sum(tok["chars"]["ssb_fr_user"]) / sum(tok["ssb_fr_user"]), 2),
                    "chars_per_tok_en": round(sum(tok["chars"]["ssb_en_user"]) / sum(tok["ssb_en_user"]), 2)})
    table[n] = row
out["table_b3"] = dict(sorted(table.items(), key=lambda kv: kv[1]["pred_i5_b3_p90"]))
print(json.dumps(out, indent=1, ensure_ascii=False))
