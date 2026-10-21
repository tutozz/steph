#!/bin/bash
# Enchaîne l'évaluation dès que pipeline.sh a écrit son GGUF : R1 d'abord, puis le candidat, même carte, même session.
set -u
W=/root/steph-ft/loop/r3t2p1
until grep -q "PIPELINE\|KO" $W/run.done 2>/dev/null; do sleep 60; done
grep -q "KO" $W/run.done && exit 1
bash $W/repo/bench/matrix/finetune/loop/r3_t2_x4/eval.sh r1 /root/steph-ft/r1/gguf/steph-speak-granite-4.0-h-350M-dpo-v1.0-Q4_K_M.gguf \
  x4-l07 $W/gguf/r3p1-x4-l07-Q4_K_M.gguf x4-l10 $W/gguf/r3p1-x4-dpo-Q4_K_M.gguf
echo "$(date +%H:%M) EVAL-DONE" >> $W/run.done
