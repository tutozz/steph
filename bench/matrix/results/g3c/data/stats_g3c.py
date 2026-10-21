#!/usr/bin/env python3
"""G3c data: counts of the retained public outputs, per family and language, and per source.

    python3 stats_g3c.py public_g3c.jsonl > stats.json
"""
import collections, json, sys

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
fam = collections.defaultdict(collections.Counter)
for r in rows:
    fam[r["family"]][r["lang"]] += 1
src = collections.Counter(r["source"].split(" (")[0] for r in rows)
out = {
    "rows": len(rows),
    "by_lang": dict(collections.Counter(r["lang"] for r in rows)),
    "by_family": {f: {"fr": c["fr"], "en": c["en"], "total": c["fr"] + c["en"]}
                  for f, c in sorted(fam.items(), key=lambda kv: -sum(kv[1].values()))},
    "by_source": dict(src.most_common()),
    "distinct_cmds": len({r["cmd"] for r in rows}),
    "exit_nonzero": sum(1 for r in rows if r["exit"] != 0),
    "with_fault": sum(1 for r in rows if r["fault"]),
    "empty_output": sum(1 for r in rows if not r["output"].strip()),
}
print(json.dumps(out, ensure_ascii=False, indent=1))
