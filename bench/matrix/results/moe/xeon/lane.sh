#!/bin/bash
# G6 : un couloir de génération du banc v3 (split test) sur le CPU de xeon, 8 fils, même lanceur et
# mêmes harnais que X3 (lane.sh de X3) : profil ft = harnais affiné (v1.0), gen = harnais générique.
# Garde X3 : port libre avant chaque run, run chargé en moins de 0,3 s écarté.
# usage : lane.sh <liste "nom gguf profil"> <port> <graines...>
set -u
D=/root/steph-ft/g6; list=$1; port=$2; shift 2
export LD_LIBRARY_PATH=/root/steph-ft/vendor/lib
while read m gguf prof; do
  [ -z "$m" ] && continue
  for sd in "$@"; do
    OUT=$D/runs/$m-test-b$sd.json
    [ -f $OUT ] && continue
    H=$D/in/x3/harness/test.json; [ $prof = gen ] && H=$D/in/x3/harness/test.generic.json
    while ss -ltn | grep -q "127.0.0.1:$port "; do echo "$(date +%T) port $port occupé" >> $D/logs/lane-$port.log; sleep 60; done
    python3 $D/bench_run.py --server /root/steph-ft/llama/llama-b11205/llama-server --model $gguf \
      --label $m-v3test-b$sd --cases $H --maxc 0 --port $port --ngl 0 --threads 8 --abort-ttft 120 \
      --payload "{\"seed\": $sd}" --out $OUT >> $D/logs/lane-$port.log 2>&1
    rc=$?
    if [ -f $OUT ] && ! python3 -c "import json,sys; sys.exit(0 if json.load(open('$OUT')).get('load_s',0) >= 0.3 else 1)"; then
      mkdir -p $D/old/rejected; mv $OUT $D/old/rejected/; rc=suspect
    fi
    echo "$(date +%T) $m test b$sd rc=$rc" >> $D/logs/lane-$port.log
  done
done < $list
echo LANEDONE >> $D/logs/lane-$port.log
