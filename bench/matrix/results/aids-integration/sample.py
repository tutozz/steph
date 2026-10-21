import json, sys, random, re
sys.path.insert(0, ".")
import score_v3
S = sys.argv[1]
cases = score_v3.load_cases("dev")
pool = []
for m in ("r1", "gemma"):
    b, a = json.load(open(f"{S}/dev-{m}-beforefix.json")), json.load(open(f"{S}/dev-{m}-after.json"))
    for f in sorted(b):
        for rid, p in sorted(b[f]["per_case"].items()):
            q = a[f]["per_case"][rid]
            norm = lambda s: re.sub(r"\.+$", ".", s.strip())
            if norm(q["said"]) != norm(p["said"]):
                pool.append((f, rid, p, q))
print("substantive changed:", len(pool), file=sys.stderr)
# dédoublonner par (rid, phrase après) : une phrase de code identique sur 6 runs compte une fois
seen, uniq = set(), []
for x in pool:
    k = (x[1], x[3]["said"])
    if k not in seen:
        seen.add(k); uniq.append(x)
print("distinct:", len(uniq), file=sys.stderr)
random.Random(20260929).shuffle(uniq)
for f, rid, p, q in uniq[:40]:
    cid, lang = score_v3.parse_row_id(rid)
    c = cases[cid]
    print(f"### {rid} [{f}] {p['score']:.2f}->{q['score']:.2f} src {p['source']}->{q['source']}")
    print("CMD:", c.get("cmd") or c.get("question", {}).get(lang), "| exit", c.get("exit"))
    out = c.get("output_raw") or "\n".join(f"$ {h['cmd']} ({h['exit']})\n{h['output_raw']}" for h in c.get("history", []))
    print("OUT:", out[-1500:])
    print("AVANT:", p["said"]); print("APRES:", q["said"]); print()
