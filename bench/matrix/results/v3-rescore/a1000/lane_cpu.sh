#!/bin/bash
# X3 : dense (R2-T1) sur le CPU de a1000 (--device none), Vulkan donnant du bruit sur ce modèle (juge du tour 2) ; un couloir par graine.
set -u
D=/root/steph-ft/loop/x3; sd=$1; port=$2
for sp in test dev; do
  OUT=$D/runs/dense-cpu-$sp-b$sd.json
  [ -f $OUT ] && continue
  python3 $D/bench_run.py --server /root/steph-ft/llama/vulkan/llama-server --model $D/gguf/dense-Q4_K_M.gguf \
    --label dense-cpu-v3$sp-b$sd --cases $D/harness/$sp.json --maxc 0 --port $port --ngl 0 --device none --threads 6 --abort-ttft 120 \
    --payload "{\"seed\": $sd}" --out $OUT >> $D/logs/lanecpu-$port.log 2>&1
  echo "$(date +%T) dense-cpu $sp b$sd rc=$?" >> $D/logs/lanecpu-$port.log
done
echo LANEDONE >> $D/logs/lanecpu-$port.log
