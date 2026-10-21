#!/bin/bash
# G3c, mélange sur la machine du corpus (hôte de la 3060) : mélange G3b inchangé (final-x4-l5 chaîne R3-T3 plus correctif
# de langue x2, `work/mix`) plus les étiquettes publiques G3c gardées par le juge, chaque fichier passé par
# `leak_check.py drop` contre les empreintes v3 au HEAD (1 105 cas), puis `scan` du mélange final. Aucun texte ne sort.
set -u
T=/mnt/backup-hdd/stephbench-tmp; B=$T/gemma/g3b/work; G=$T/g3c; L=$G/labels; R=$G/repo; M=$G/mix
LC="nice -n 19 python3 $R/bench/matrix/v3/tools/leak_check.py"
mkdir -p $M/clean && cd $M
for f in $B/mix/train.jsonl $B/mix/val.jsonl; do
  $LC drop $L/v3prints-head.json $f clean/g3b-$(basename $f) > clean/drop-g3b-$(basename $f .jsonl).json
done
python3 - "$L" <<'PY'
import json, sys
L = sys.argv[1]
for part in ("train", "val"):
    with open(f"public-{part}.jsonl", "w") as f:
        for line in open(f"{L}/public_{part}.jsonl"):
            r = json.loads(line)
            f.write(json.dumps({"messages": r["messages"], "source": "g3c_public_" + r["lang"]}, ensure_ascii=False) + "\n")
PY
for p in train val; do $LC drop $L/v3prints-head.json public-$p.jsonl clean/public-$p.jsonl > clean/drop-public-$p.json; done
cat clean/g3b-train.jsonl clean/public-train.jsonl > train.jsonl
cat clean/g3b-val.jsonl clean/public-val.jsonl > val.jsonl
$LC scan $L/v3prints-head.json leak-mix.json train.jsonl val.jsonl > leak.log 2>&1
python3 - <<'PY' > counts.json
import collections, json
out = {}
for p in ("train", "val"):
    rows = [json.loads(l) for l in open(f"{p}.jsonl")]
    out[p] = {"rows": len(rows), "by_source": dict(collections.Counter(r["source"] for r in rows).most_common())}
print(json.dumps(out, ensure_ascii=False))
PY
sha256sum train.jsonl val.jsonl clean/public-train.jsonl clean/public-val.jsonl > SHA256SUMS
cat clean/drop-*.json counts.json; tail -1 leak.log
