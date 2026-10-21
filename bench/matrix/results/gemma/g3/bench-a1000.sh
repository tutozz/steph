#!/bin/bash
# G3 : banc v3 dev rapide sur A1000 Vulkan (même serveur et harnais générique que X3), bench_run.py au HEAD. bench.sh <nom> <gguf> <graine> [port]
set -u
W=/root/steph-ft/g3; OUT=$W/runs/$1-dev-b$3.json
[ -f $OUT ] && exit 0
until [ -f $2 ]; do sleep 30; done
python3 $W/bench_run.py --server /root/steph-ft/llama/vulkan/llama-server --model $2 --label $1-v3dev-b$3 --cases $W/dev.generic.json \
  --maxc 0 --port ${4:-8981} --ngl 99 --abort-ttft 120 --payload "{\"seed\": $3}" --out $OUT >> $W/logs/bench-$1.log 2>&1
echo "$(date +%T) $1 b$3 rc=$?" >> $W/logs/bench.done
