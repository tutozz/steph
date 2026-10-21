#!/bin/sh
# bancs de vitesse et mémoire : bench/matrix/bench_run.py du dépôt cloné, harnais non modifié
export HOME=/root/steph-z9/home CUDA_DEVICE_ORDER=PCI_BUS_ID
S=$HOME/.local/share/steph/src
M=$HOME/.local/share/steph/models
O=/root/steph-z9/out
SMALL=$M/steph-speak-granite-4.0-h-350M-sft-v2.0-Q4_K_M.gguf
BASE=$M/steph-speak-gemma-4-E2B-sft-v2.0-off-ple3.gguf
run() { # label model ngl ctx visible
  nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader > $O/$1.vram-before.txt
  CUDA_VISIBLE_DEVICES=$5 nice -n 10 python3 $S/bench/matrix/bench_run.py --server /root/steph-z9/bin/llama-server --model $2 --label $1 --out $O/$1.json --ngl $3 --ctx $4 --parallel 2 --threads 6 --abort-ttft 600 --timeout 600 --port 8830 > $O/$1.log 2>&1
  nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader > $O/$1.vram-after.txt
}
run z9-small-gpu $SMALL 99 8192 1
run z9-small-cpu $SMALL 0 8192 -1
run z9-base-cpu $BASE 0 32768 -1
echo done > $O/perf.done
