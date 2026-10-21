#!/bin/bash
# R3-T3 étape 2, partie SFT : 4 graines par bras (kd puis témoin ce, une SFT à la fois sur la 3060),
# soupes, GGUF, banc v3 dev 3 graines des deux soupes. Paires et DPO lancés à part (juge 9B requis).
set -u
W=/mnt/backup-hdd/stephbench-tmp/loop/r3t3; K=$W/repo/bench/matrix/finetune/loop/r3t3; C="bash $K/chain.sh"
cd $W
KO0=$(grep -c "TOPK KO" run.done)
until [ -f work/topk-s42.pt ]; do [ $(grep -c "TOPK KO" run.done) -gt $KO0 ] && exit 1; sleep 60; done
# une SFT à la fois : un juge 9B d'une autre théorie occupe 6,1 Go de la carte
for s in 42 7 123 2024; do $C ssft kd $s; done
$C ssoup kd || exit 1
$C bench kd-sft $W/gguf/r3t3-kd-sft-Q4_K_M.gguf
for s in 42 7 123 2024; do $C ssft ce $s; done
$C ssoup ce || exit 1
$C bench ce-sft $W/gguf/r3t3-ce-sft-Q4_K_M.gguf
echo "$(date +%H:%M) SOUPES BANQUÉES" >> run.done
