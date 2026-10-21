#!/bin/bash
# R3-T3 : témoin ce après ses 4 SFT : soupe, GGUF, banc v3 dev 3 graines.
W=/mnt/backup-hdd/stephbench-tmp/loop/r3t3; C="bash $W/repo/bench/matrix/finetune/loop/r3t3/chain.sh"
cd $W
for s in 42 7 123 2024; do until [ -f $W/ce/sft-s$s/adapter/adapter_model.safetensors ]; do sleep 60; done; done
$C ssoup ce || exit 1
$C bench ce-sft $W/gguf/r3t3-ce-sft-Q4_K_M.gguf
echo "$(date +%H:%M) CE FINI" >> run.done
