#!/bin/bash
# R3-T1, suite : même banc sur l'iGPU Intel (Vulkan0) de la machine, après runs.sh.
set -u
D=/root/steph-ft/loop/r3t1; cd $D
while ! grep -q DONE logs/runs.log 2>/dev/null; do sleep 20; done
VK=$D/bin/vk/llama-b11232/llama-server
PAY='{"temperature": 0, "top_k": 1, "seed": 7}'
run() { local lab=$1 dev=$2 m=$3; shift 3
  [ -f runs/$lab.json ] && return
  env "$@" python3 bench_run.py --server $VK --model $D/$m.gguf --label $lab --cases dev50.json --maxc 0 \
    --port 8976 --ngl 99 --threads 8 --device $dev --payload "$PAY" --extra "--cache-ram 0" --out runs/$lab.json >> logs/runs2.log 2>&1
}
run dense-intel Vulkan0 dense X=1
run r1-intel Vulkan0 r1 X=1
run dense-nv-explicit Vulkan1 dense X=1
echo DONE >> logs/runs2.log
