#!/bin/bash
# G4 : banc v3 test (harnais identique à G3, md5 1ea3b078), 3080 CUDA, file de travaux partagée.
#   lane.sh <port> ; ligne de la file : <variante> <graine> ; GGUF gguf/<variante>.gguf, visible quand gguf/<variante>.ok existe.
#   Disque de la 3080 à 18 Go libres : le GGUF est effacé après son travail, sauf si gguf/<variante>.keep existe.
set -u
W=/root/steph-ft/g4; port=$1; Q=$W/jobs.q
while :; do
  job=$(flock $Q.lock sh -c "head -1 $Q; sed -i 1d $Q")
  [ -z "$job" ] && break
  set -- $job; m=$1; sd=$2
  OUT=$W/runs/g4-$m-test-b$sd.json
  until [ -f $W/gguf/$m.ok ]; do sleep 30; done
  if [ ! -f $OUT ]; then
    while [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)" -lt 2500 ]; do sleep 60; done
    nice -n 5 python3 $W/repo/bench/matrix/bench_run.py --server /root/steph-ft/llama.cpp/build/bin/llama-server \
      --model $W/gguf/$m.gguf --label g4-$m-v3test-cuda-b$sd --cases $W/harness/test.generic.json \
      --maxc 0 --port $port --ngl 99 --abort-ttft 120 --payload "{\"seed\": $sd}" --out $OUT >> $W/logs/lane-$port.log 2>&1
    echo "$(date +%T) $m b$sd rc=$?" >> $W/logs/done.log
  fi
  [ -f $W/gguf/$m.keep ] || { rm -f $W/gguf/$m.gguf $W/gguf/$m.ok; echo "$(date +%T) $m GGUF effacé" >> $W/logs/done.log; }
done
echo "$(date +%T) LANE $port FIN" >> $W/logs/done.log
