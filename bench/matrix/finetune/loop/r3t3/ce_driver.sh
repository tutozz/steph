#!/bin/bash
# R3-T3 : témoin ce en parallèle du bras kd dès que la carte a la place de deux SFT (moins de 7 Go occupés).
W=/mnt/backup-hdd/stephbench-tmp/loop/r3t3; C="bash $W/repo/bench/matrix/finetune/loop/r3t3/chain.sh"
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 7000 ]; do sleep 60; done
echo "$(date +%H:%M) témoin ce lancé en parallèle" >> $W/run.done
for s in 2024 123 7 42; do $C ssft ce $s; done
