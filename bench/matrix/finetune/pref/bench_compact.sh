#!/bin/bash
# bench_compact.sh <gguf> <label> : banc 36 cas granite200 TRAIN_SYSTEM, 3 graines, harnais P15 (payload graine seule, maxc 0)
set -u
G=$1; L=$2; P=${WORK:-/root/steph-ft/p17}
cd /root/steph-ft/ft/bench
for sd in 7 42 123; do
  OUT=$P/bench/$L-b$sd.json
  [ -f $OUT ] || python3 bench_run.py --server /root/steph-ft/llama.cpp/build/bin/llama-server --model $G --label $L-b$sd \
    --cases $P/cases_compact_granite200_train.json --maxc 0 --port 8960 --ngl 99 --payload "{\"seed\": $sd}" --out $OUT >> $P/logs/$L-bench.log 2>&1
done
echo "BANC $L" >> $P/bench.done
