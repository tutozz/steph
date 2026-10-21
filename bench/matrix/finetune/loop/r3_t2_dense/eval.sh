#!/bin/bash
# R3-T2 partie 2 : le banc v3 dev 0db04fa du dense x4 passe dans les couloirs de la partie 3 (p3_dense.sh, ports 8971-8973,
# graines 7, 42, 123), dans la même session et sur la même carte que R1 (r1s2) et que le dense R2-T1 : pas de second passage
# ici. Reste le banc 36 et Steph Speak Bench (run_eval_k3.sh de R1, ports fixes 8960 et 8894, jamais en même temps qu'une
# autre partie) ; R1 et les Granite H y passent chez la partie 3.
set -u
W=/root/steph-ft/loop/r3t2p2; R=$W/repo; G=$W/gguf/r3p2-dense-x4-l10-Q4_K_M.gguf
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
cd $W; mkdir -p logs
sha256sum $G >> $W/gguf-sha256.txt
while pgrep -f "run_eval_k3.sh" > /dev/null || ss -ltn | grep -qE ":(8960|8894) "; do sleep 60; done
K3=$W bash $R/bench/matrix/finetune/pref/run_eval_k3.sh $G dense-x4
note "EVAL-DONE"
