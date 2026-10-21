#!/bin/bash
# G3c-t9, mélange sur la machine du corpus (hôte de la 3060), après la mise à jour T9 : final-t9 remplace final-x4-l5.
# Base : mélange de G5b (`g5b/mix`), chaîne de G3b sur final-t9 (compose_train, compose_k3 --max-chars 587,
# compose_r1 --repeat en_summary=2 --keep detail=0.5, extra vide), correctif de langue G3b x2, corrections T9 x1,
# contamination par ligne et audit_pii déjà passés ; on y ajoute les étiquettes publiques G3c déjà filtrées
# (`g3c/mix/clean/public-*.jsonl`). Contrôles refaits sur le tout : scan contre les empreintes v3 de G3c, audit_pii,
# prompts système reconnus par `to_generic`. Aucun texte ne sort.
set -u
T=/mnt/backup-hdd/stephbench-tmp; G=$T/g3c; R=$G/repo; M=$G/mix-t9; B=$T/g5b/mix; P=$G/mix/clean
PY3=$T/g5b/py/cpython-3.13.15-linux-x86_64-gnu/bin/python3.13
[ -f $M/train.jsonl ] && { echo "déjà fait"; exit 0; }
mkdir -p $M && cd $M
grep -q "94562b16a16f3dd36088cec50e20ff329af45827d054b9d6c756f4b8457bd911  mix/train.jsonl" $T/g5b/logs/mix-sha.txt \
  && echo "94562b16a16f3dd36088cec50e20ff329af45827d054b9d6c756f4b8457bd911  $B/train.jsonl" | sha256sum -c --quiet \
  || { echo "ARRÊT : base G5b modifiée"; exit 1; }
cat $B/train.jsonl $P/public-train.jsonl > train.jsonl
cat $B/val.jsonl $P/public-val.jsonl > val.jsonl
nice -n 19 python3 $R/bench/matrix/v3/tools/leak_check.py scan $G/labels/v3prints-head.json leak-mix.json train.jsonl val.jsonl \
  > leak.log 2>&1
$PY3 $R/bench/matrix/finetune/audit_pii.py train.jsonl val.jsonl > pii.log 2>&1; echo "audit_pii rc=$?" >> pii.log
# to_generic du dépôt qui entraîne (copie G3b), pas de la copie partielle g3c/repo
PYTHONPATH=$T/gemma/g3b/repo/src $PY3 - $T/gemma/g3b/repo <<'PY' > counts.json
import collections, json, sys
sys.path.insert(0, sys.argv[1] + "/bench/matrix/finetune/gemma")
from gemma_format import to_generic
out = {}
for p in ("train", "val"):
    rows = [json.loads(l) for l in open(f"{p}.jsonl")]
    unknown = sum(not to_generic(r["messages"])[1] for r in rows)
    src = collections.Counter(r.get("source", "?") for r in rows)
    public = sum(n for s, n in src.items() if s.startswith("g3c_public"))
    out[p] = {"rows": len(rows), "unknown_system": unknown, "public_share": round(public / len(rows), 3),
              "by_source": dict(src.most_common())}
print(json.dumps(out, ensure_ascii=False))
PY
sha256sum train.jsonl val.jsonl > SHA256SUMS
cat counts.json; tail -1 pii.log; tail -1 leak.log | cut -c1-120
