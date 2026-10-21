#!/bin/bash
# R3-T1 : variante exacte (ffn_up F32 / 4, couches 2 et 3), puis KL par jeton de toutes les variantes contre le dense CPU d origine.
set -u
D=/root/steph-ft/loop/r3t1; cd $D
VK=$D/bin/vk/llama-b11232/llama-server; CPU=$D/bin/cpu/llama-b11232/llama-server; OLD=/root/steph-ft/llama/vulkan/llama-server
PAY="{\"temperature\": 0, \"top_k\": 1, \"seed\": 7}"
run() { local lab=$1 srv=$2 ngl=$3 m=$4; shift 4
  [ -f runs/$lab.json ] && return
  env "$@" python3 bench_run.py --server $srv --model $D/$m.gguf --label $lab --cases dev50.json --maxc 0 \
    --port 8977 --ngl $ngl --threads 8 --device ${DEV:-Vulkan1} --payload "$PAY" --extra "--cache-ram 0" --out runs/$lab.json >> logs/runs4.log 2>&1
}
DEV=none run foldf-cpu $CPU 0 foldf X=1
run foldf-vk $VK 99 foldf X=1
run foldf-old-vk $OLD 99 foldf X=1
DEV=Vulkan0 run foldf-intel $VK 99 foldf X=1
PV=bin/vk/llama-b11232/llama-perplexity; PC=bin/cpu/llama-b11232/llama-perplexity
for m in fold1 fold2 foldf; do
  [ -f kl/$m-cpu.log ] || $PC -m $m.gguf -f kltext.txt -c 512 -b 512 -t 8 --kl-divergence-base kl/dense-cpu.base --kl-divergence > kl/$m-cpu.log 2>&1
  [ -f kl/$m-nv.log ] || $PV -m $m.gguf -f kltext.txt -c 512 -b 512 -t 8 -ngl 99 --device Vulkan1 --kl-divergence-base kl/dense-cpu.base --kl-divergence > kl/$m-nv.log 2>&1
done
echo DONE >> logs/runs4.log
