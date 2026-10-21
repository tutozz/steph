#!/bin/bash
# R3-T1 : GGUF repliés (ffn_up / 2^k, ffn_down x 2^k, couches 2 et 3), CPU contre Vulkan coopmat actif.
set -u
D=/root/steph-ft/loop/r3t1; cd $D
VK=$D/bin/vk/llama-b11232/llama-server; CPU=$D/bin/cpu/llama-b11232/llama-server; OLD=/root/steph-ft/llama/vulkan/llama-server
PAY="{\"temperature\": 0, \"top_k\": 1, \"seed\": 7}"
run() { local lab=$1 srv=$2 ngl=$3 m=$4; shift 4
  [ -f runs/$lab.json ] && return
  env "$@" python3 bench_run.py --server $srv --model $D/$m.gguf --label $lab --cases dev50.json --maxc 0 \
    --port 8977 --ngl $ngl --threads 8 --device ${DEV:-Vulkan1} --payload "$PAY" --extra "--cache-ram 0" --out runs/$lab.json >> logs/runs3.log 2>&1
}
DEV=none run fold1-cpu $CPU 0 fold1 X=1
run fold1-vk $VK 99 fold1 X=1
DEV=none run fold2-cpu $CPU 0 fold2 X=1
run fold2-vk $VK 99 fold2 X=1
run fold2-old-vk $OLD 99 fold2 X=1
run fold2-vk-ngl0 $VK 0 fold2 X=1
DEV=Vulkan0 run fold2-intel $VK 99 fold2 X=1
echo DONE >> logs/runs3.log
