#!/bin/bash
# R3-T2 partie 1 : banc v3 dev 0db04fa (dev.json sha256 0b220cac…, 3 graines), puis banc 36 et Steph Speak Bench
# (run_eval_k3.sh de R1), sur la 3080 CUDA, R1 et le candidat dans la même session.
#   eval.sh <étiquette> <gguf> [...]
set -u
W=/root/steph-ft/loop/r3t2p1; R=$W/repo; B=/root/steph-ft/llama.cpp/build/bin
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
cd $W; mkdir -p runs logs
while [ $# -ge 2 ]; do
  L=$1; G=$2; shift 2
  sha256sum $G >> $W/gguf-sha256.txt
  for sd in 7 42 123; do
    OUT=$W/runs/$L-dev-b$sd.json
    [ -f $OUT ] || python3 $R/bench/matrix/bench_run.py --server $B/llama-server --model $G --label $L-v3dev-b$sd \
      --cases $R/bench/matrix/v3/harness/dev.json --maxc 0 --port 8962 --ngl 99 --payload "{\"seed\": $sd}" \
      --out $OUT >> $W/logs/eval-$L-v3.log 2>&1
  done
  K3=$W bash $R/bench/matrix/finetune/pref/run_eval_k3.sh $G $L
  note "EVAL $L"
done
