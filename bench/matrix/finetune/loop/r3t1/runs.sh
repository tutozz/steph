#!/bin/bash
# R3-T1 : 50 cas dev en glouton, dense et R1, CPU contre Vulkan, réglages en variables.
set -u
D=/root/steph-ft/loop/r3t1; cd $D
VK=$D/bin/vk/llama-b11232/llama-server; CPU=$D/bin/cpu/llama-b11232/llama-server; OLD=/root/steph-ft/llama/vulkan/llama-server
PAY='{"temperature": 0, "top_k": 1, "seed": 7}'
run() { # label server ngl model env...
  local lab=$1 srv=$2 ngl=$3 m=$4; shift 4
  [ -f runs/$lab.json ] && return
  env "$@" python3 bench_run.py --server $srv --model $D/$m.gguf --label $lab --cases dev50.json --maxc 0 \
    --port 8975 --ngl $ngl --threads 8 --payload "$PAY" --extra "--cache-ram 0" --out runs/$lab.json >> logs/runs.log 2>&1
}
run dense-cpu $CPU 0 dense X=1
run dense-vk $VK 99 dense X=1
run dense-vk-nocoopmat $VK 99 dense GGML_VK_DISABLE_COOPMAT=1
run dense-vk-ngl0 $VK 0 dense X=1
run dense-old-nocoopmat $OLD 99 dense GGML_VK_DISABLE_COOPMAT=1
run r1-cpu $CPU 0 r1 X=1
run r1-vk $VK 99 r1 X=1
run r1-vk-nocoopmat $VK 99 r1 GGML_VK_DISABLE_COOPMAT=1
echo DONE >> logs/runs.log
