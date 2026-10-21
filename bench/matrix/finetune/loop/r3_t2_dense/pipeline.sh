#!/bin/bash
# R3-T2 partie 2 : enchaînement sur la 3080 partagée (partie 1, R3-C1). Le SFT dense attend la fin des paires de la partie 1,
# dont le juge 9B demande presque toute la carte ; chaque étape attend 4,5 Go libres et reprend après un OOM, comme R2-T1.
# Relance de 19:55 : le SFT dense (4,1 Go) et le DPO de la partie 1 (5,6 Go) ne tiennent pas ensemble sur 9,6 Go ; le SFT
# attend donc la fin de run_k3.sh de la partie 1 et 5,5 Go libres.
set -u
W=/root/steph-ft/loop/r3t2p2; P1=/root/steph-ft/loop/r3t2p1; C="bash $W/repo/bench/matrix/finetune/loop/r3_t2_dense/chain.sh"
cd $W
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
retry() {  # étape, fichier attendu, commande...
  local what=$1 want=$2; shift 2
  for i in $(seq 30); do
    [ -e $want ] && return 0
    until [ $(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits) -ge ${NEED:-5500} ]; do sleep 60; done
    "$@"
    [ -e $want ] && return 0
    note "REPRISE $what ($i)"; sleep 180
  done
  note "ABANDON $what"; exit 1
}
note "ATTENTE paires partie 1"
until [ -f $P1/x4/pairs-counts.json ]; do sleep 120; done
note "DÉPART"
while pgrep -f "r3t2p1/repo/bench/matrix/finetune/pref/run_k3.sh" > /dev/null; do sleep 60; done
note "DPO partie 1 fini, SFT dense"
for s in 42 7 123; do
  retry "sft s$s" sft-s$s/adapter/adapter_model.safetensors env SFT_SEEDS=$s $C sft
done
retry soup gguf/r3p2-dense-x4-sft-Q4_K_M.gguf $C soup
$C pairs || { note "PAIRES KO"; exit 1; }
for s in 42 7 123; do
  retry "dpo s$s" dpo-s$s/adapter/adapter_model.safetensors $C dpo
done
retry "fusion 1.0" gguf/r3p2-dense-x4-l10-Q4_K_M.gguf $C merge 1.0
note PIPELINE
bash $W/repo/bench/matrix/finetune/loop/r3_t2_dense/eval.sh
