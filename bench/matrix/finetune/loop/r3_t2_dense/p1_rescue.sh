#!/bin/bash
# R3-T2 partie 2 : la partie 2 a besoin des paires DPO de la partie 1. Si la chaîne de la partie 1 meurt (OOM sur la 3080
# partagée), elle est relancée telle quelle (pipeline.sh idempotent, 3 essais, même attente de 9 Go libres que launch.sh),
# puis son évaluation (after.sh sort dès qu'il lit KO) est rejouée avec les mêmes arguments.
set -u
P1=/root/steph-ft/loop/r3t2p1; S=$P1/repo/bench/matrix/finetune/loop/r3_t2_x4
note() { echo "$(date +%H:%M) $*" >> $P1/run.done; }
alive() { pgrep -f "r3_t2_x4/pipeline.sh" > /dev/null; }
for i in 1 2 3; do
  while alive; do sleep 60; done
  grep -q "PIPELINE" $P1/run.done && break
  until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge 9000 ]; do sleep 60; done
  alive && continue
  note "RELANCE $i par la partie 2"
  bash $S/pipeline.sh
done
grep -q "PIPELINE" $P1/run.done || exit 1
pgrep -f "r3_t2_x4/after.sh|r3_t2_x4/eval.sh" > /dev/null && exit 0
grep -q "EVAL-DONE" $P1/run.done && exit 0
bash $S/eval.sh r1 /root/steph-ft/r1/gguf/steph-speak-granite-4.0-h-350M-dpo-v1.0-Q4_K_M.gguf \
  x4-l07 $P1/gguf/r3p1-x4-l07-Q4_K_M.gguf x4-l10 $P1/gguf/r3p1-x4-dpo-Q4_K_M.gguf
echo "$(date +%H:%M) EVAL-DONE" >> $P1/run.done
