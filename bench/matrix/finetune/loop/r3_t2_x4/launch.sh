#!/bin/bash
# R3-T2 partie 1 : attend que la 3080 soit libre (serveur orphelin arrêté par son propriétaire, 9 Go libres),
# arrête Ollama s'il tourne (relancé à la fin par close.sh), puis lance pipeline.sh.
set -u
W=/root/steph-ft/loop/r3t2p1
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
note "ATTENTE 3080"
until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge 9000 ]; do sleep 60; done
if systemctl is-active --quiet ollama; then systemctl stop ollama && touch $W/ollama.stopped && note "OLLAMA ARRÊTÉ"; fi
note "DÉPART"
bash $W/repo/bench/matrix/finetune/loop/r3_t2_x4/pipeline.sh
