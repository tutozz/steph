#!/bin/bash
# R3-T3 étape 1 : attend la 3060 libre (10 Go), puis enseignant graine 42, GGUF, banc v3 dev 3 graines.
W=/mnt/backup-hdd/stephbench-tmp/loop/r3t3; cd $W
echo "$(date +%H:%M) ATTENTE 3060" >> run.done
until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 1500 ]; do sleep 60; done
echo "$(date +%H:%M) DÉPART" >> run.done
bash chain.sh teacher 42 && bash chain.sh teacher-gguf 42 && bash chain.sh bench teacher-s42 $W/gguf/r3t3-teacher-s42-Q4_K_M.gguf
