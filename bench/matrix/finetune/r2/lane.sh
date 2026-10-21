#!/bin/bash
# R2 : banc v3 au commit a52223c (après X5), split donné, 3080 CUDA b11205, un couloir par graine,
# v1.0 et R2 dans la même session, même harnais.
#   lane.sh <split> <port> <graine> <étiquette> [...] ; modèle gguf/<étiquette>-Q4_K_M.gguf
set -u
W=/root/steph-ft/r2; split=$1; port=$2; sd=$3; shift 3
for m in "$@"; do
  OUT=$W/runs/$m-$split-b$sd.json
  [ -f $OUT ] && continue
  nice -n 5 python3 $W/repo/bench/matrix/bench_run.py --server /root/steph-ft/llama.cpp/build/bin/llama-server \
    --model $W/gguf/$m-Q4_K_M.gguf --label $m-v3$split-cuda-b$sd --cases $W/repo/bench/matrix/v3/harness/$split.json \
    --maxc 0 --port $port --ngl 99 --payload "{\"seed\": $sd}" --out $OUT >> $W/logs/lane-$port.log 2>&1
  echo "$(date +%T) $m $split b$sd rc=$?" >> $W/logs/lane-$port.log
done
echo "$(date +%T) DONE $split $*" >> $W/logs/lane-$port.log
