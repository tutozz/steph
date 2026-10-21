#!/bin/bash
# KL par jeton, Vulkan contre CPU, sur le texte des 50 cas dev (traitement de prompt, là où tournent les matmul coopmat).
set -u
D=/root/steph-ft/loop/r3t1; cd $D
while ! grep -q DONE logs/runs2.log 2>/dev/null; do sleep 20; done
VK=bin/vk/llama-b11232/llama-perplexity; CPU=bin/cpu/llama-b11232/llama-perplexity
for m in dense r1; do
  [ -f kl/$m-cpu.base ] || $CPU -m $m.gguf -f kltext.txt -c 512 -b 512 -t 8 --kl-divergence-base kl/$m-cpu.base > kl/$m-cpu.log 2>&1
  for cfg in "nv|Vulkan1|X=1" "nv-nocoopmat|Vulkan1|GGML_VK_DISABLE_COOPMAT=1" "intel|Vulkan0|X=1" "cpu2|none|X=1"; do
    IFS='|' read lab dev e <<< "$cfg"
    env $e $VK -m $m.gguf -f kltext.txt -c 512 -b 512 -t 8 -ngl 99 --device $dev --kl-divergence-base kl/$m-cpu.base --kl-divergence > kl/$m-$lab.log 2>&1
  done
done
echo DONE >> kl/done
