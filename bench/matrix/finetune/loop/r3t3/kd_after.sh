#!/bin/bash
# R3-T3 : bras kd après les 4 SFT : soupe, banc dev, paires (juge 9B sur cet hôte), DPO, fusion 0,7, banc dev.
W=/mnt/backup-hdd/stephbench-tmp/loop/r3t3; C="bash $W/repo/bench/matrix/finetune/loop/r3t3/chain.sh"
cd $W
[ -f $W/gguf/r3t3-kd-sft-Q4_K_M.gguf ] || $C ssoup kd || exit 1
[ -f $W/runs/kd-sft-dev-b123.json ] || $C bench kd-sft $W/gguf/r3t3-kd-sft-Q4_K_M.gguf
# juge : le serveur 9B de R3-T4 (port 8984, même GGUF 03b74727) occupe la carte ; pas la place pour un second
JPORT=${JPORT:-8984} $C spairs kd || exit 1
$C sdpo kd || exit 1
$C bench kd-l07 $W/gguf/r3t3-kd-l07-Q4_K_M.gguf
echo "$(date +%H:%M) KD FINI" >> run.done
