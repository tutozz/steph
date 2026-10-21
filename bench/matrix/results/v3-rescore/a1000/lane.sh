#!/bin/bash
# X3 : un couloir = une liste de modèles x des graines, test puis dev, harnais v3 figé au commit 145c373
# (échantillonnage de production). Profil ft : harnais affiné (TRAIN_SYSTEM) ; gen : harnais générique
# (SUMMARY_SYSTEM), format de production de chaque modèle.
# Garde : un llama-server orphelin sur le port ferait répondre un autre modèle (vu le 28/09 : chargement
# en 0,02 s) ; on attend un port libre, et un résultat chargé en moins de 0,3 s est mis de côté.
set -u
D=/root/steph-ft/loop/x3; list=$1; port=$2; shift 2
while read m gguf prof ngl; do
  [ -z "$m" ] && continue
  for sd in "$@"; do for sp in test dev; do
    OUT=$D/runs/$m-$sp-b$sd.json
    [ -f $OUT ] && continue
    H=$D/harness/$sp.json; [ $prof = gen ] && H=$D/harness/$sp.generic.json
    until [ -f $gguf ]; do sleep 30; done
    while ss -ltn | grep -q "127.0.0.1:$port "; do echo "$(date +%T) port $port occupé" >> $D/logs/lane-$port.log; sleep 60; done
    python3 $D/bench_run.py --server /root/steph-ft/llama/vulkan/llama-server --model $gguf \
      --label $m-v3$sp-b$sd --cases $H --maxc 0 --port $port --ngl $ngl --abort-ttft 120 \
      --payload "{\"seed\": $sd}" --out $OUT >> $D/logs/lane-$port.log 2>&1
    rc=$?
    if ! python3 -c "import json,sys; sys.exit(0 if json.load(open('$OUT')).get('load_s',0) >= 0.3 else 1)"; then
      mkdir -p $D/old/rejected; mv $OUT $D/old/rejected/; rc=suspect
    fi
    echo "$(date +%T) $m $sp b$sd rc=$rc" >> $D/logs/lane-$port.log
  done; done
done < $list
echo LANEDONE >> $D/logs/lane-$port.log
