#!/bin/bash
# R3-T2 partie 3 : reprise de pipeline.sh après l'OOM de SFT s7 (3080 partagée avec R3-C1), une graine SFT à la fois,
# puis banc v3 dev figé 0db04fa (R1 rejoué dans la même session, 3 couloirs), puis banc 36 et Steph Speak Bench.
# Les étapes de run_k3.sh sautent ce qui existe déjà ; chaque tentative attend la mémoire GPU libre nécessaire.
set -u
W=/root/steph-ft/loop/r3t2p1; D=/root/steph-ft/loop/r3t2p3; R=$W/repo
note() { echo "$(date +%H:%M) $*" >> $D/run.done; }
free_mib() { nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits; }
k3_busy() { pgrep -f "r3t2p1/repo/bench/matrix/finetune/pref/run_k3.sh" > /dev/null; }
port_busy() { ss -ltn | grep -q ":$1 "; }

note "ATTENTE fin de la chaîne partie 1"
while k3_busy; do sleep 60; done
for try in 1 2 3 4 5 6; do
  grep -q PIPELINE $W/run.done && break
  missing=""
  for s in 42 7 123 2024; do [ -f $W/x4/sft-s$s/adapter/adapter_model.safetensors ] || missing="$missing $s"; done
  need=$([ -n "$missing" ] && echo 4500 || echo 7500)
  note "TENTATIVE $try, SFT manquants :${missing:- aucun}, attente $need Mo libres"
  until [ "$(free_mib)" -ge $need ]; do sleep 60; done
  SFT_PAIRS="${missing:-42}" bash $R/bench/matrix/finetune/loop/r3_t2_x4/pipeline.sh
done
grep -q PIPELINE $W/run.done || { note "CHAÎNE KO après 6 tentatives"; exit 1; }
note "GGUF prêts"

ln -sfn $W/repo $D/repo
ln -sf /root/steph-ft/r1/gguf/steph-speak-granite-4.0-h-350M-dpo-v1.0-Q4_K_M.gguf $D/gguf/r1s2-Q4_K_M.gguf
ln -sf $W/gguf/r3p1-x4-l07-Q4_K_M.gguf $D/gguf/x4-l07-Q4_K_M.gguf
ln -sf $W/gguf/r3p1-x4-dpo-Q4_K_M.gguf $D/gguf/x4-l10-Q4_K_M.gguf
for g in $D/gguf/*.gguf; do echo "$(sha256sum < $(readlink -f $g) | cut -c1-64) $(ls -lL $g | awk '{print $5}') $(basename $g)"; done > $D/gguf-sha256.txt
# R1 rejoué dans cette session, sous une autre étiquette que la passe de 16:47
for p in 8971:7 8972:42 8973:123; do
  bash $D/lane.sh ${p%%:*} ${p##*:} r1s2 x4-l07 x4-l10 &
done
wait
note "DEV FAIT"
for m in r1s2 x4-l07 x4-l10; do
  while port_busy 8960 || port_busy 8894; do sleep 30; done
  K3=$D bash $R/bench/matrix/finetune/pref/run_eval_k3.sh $(readlink -f $D/gguf/$m-Q4_K_M.gguf) $m
done
note "EVAL-DONE"
