#!/bin/bash
# R2-T1 : enchaîne SFT (une graine à la fois, la 3080 est partagée), soupe, DPO et fusion, avec reprise après un OOM.
set -u
W=/root/steph-ft/loop/r2t1
cd $W
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
retry() {  # étape, fichier attendu, commande...
  local what=$1 want=$2; shift 2
  for i in $(seq 30); do
    [ -e $want ] && return 0
    # attend 4,5 Go libres sur la carte partagée
    until [ $(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits) -ge 4500 ]; do sleep 60; done
    "$@"
    [ -e $want ] && return 0
    note "REPRISE $what ($i)"; sleep 120
  done
  note "ABANDON $what"; exit 1
}
while pgrep -f "r2t1/repo/bench/matrix/finetune/train_sft.py" > /dev/null; do sleep 60; done
for s in 7 42 123; do
  retry "sft s$s" sft-s$s/adapter/adapter_model.safetensors env SFT_SEEDS=$s bash chain.sh sft
done
retry soup gguf/r2t1-sft-Q4_K_M.gguf bash chain.sh soup
for s in 42 7 123; do
  retry "dpo s$s" dpo-s$s/adapter/adapter_model.safetensors bash chain.sh dpo
done
retry "fusion 1.0" gguf/r2t1-dpo-l10-Q4_K_M.gguf bash chain.sh merge 1.0
note PIPELINE
