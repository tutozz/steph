#!/bin/bash
# R2-T1 : banc v3 dev (3 graines), banc 36 et Steph Speak Bench, même carte (3080 CUDA), même session.
#   eval.sh <label> <gguf> [...]   ex. eval.sh r1 /root/steph-ft/r1/gguf/...gguf r2t1-dpo-l10 gguf/r2t1-dpo-l10-Q4_K_M.gguf
set -u
W=/root/steph-ft/loop/r2t1; R=$W/repo; B=/root/steph-ft/llama.cpp/build/bin
cd $W
while [ $# -ge 2 ]; do
  L=$1; G=$2; shift 2
  sha256sum $G >> $W/gguf-sha256.txt
  for sd in 7 42 123; do
    OUT=$W/runs/$L-dev-b$sd.json
    [ -f $OUT ] || python3 $R/bench/matrix/bench_run.py --server $B/llama-server --model $G --label $L-v3dev-b$sd \
      --cases $R/bench/matrix/v3/harness/dev.json --maxc 0 --port 8961 --ngl 99 --payload "{\"seed\": $sd}" \
      --out $OUT >> $W/logs/eval-$L-v3.log 2>&1
  done
  K3=$W bash $R/bench/matrix/finetune/pref/run_eval_k3.sh $G $L
  echo "$(date +%H:%M) EVAL $L" >> $W/run.done
done
