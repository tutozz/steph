#!/bin/bash
# G3c, réaffinage sur l'hôte de la 3060 (le mélange porte le corpus, il ne quitte pas la machine) : recette G3b exacte
# (LoRA bf16 r16 α32, lr 1e-4, 2 époques, lot 16, micro 4, maxlen 2048, arrêt anticipé, prompt générique), graines 42 puis 7.
# Code : copie du dépôt de G3b sur cette machine (scripts gemma identiques au HEAD ; src du HEAD exige Python 3.12, le venv est en 3.11).
#   train-3060.sh [PID à attendre]   (la carte est partagée : on attend la fin du PID donné, puis une carte vide)
set -u
T=/mnt/backup-hdd/stephbench-tmp; G=$T/g3c; W=$G/train; R=$T/gemma/g3b/repo; M=$G/mix
note() { echo "$(date '+%d %H:%M') $*" >> $W/run.done; }
mkdir -p $W/logs; cd $W
sha256sum -c --quiet <(grep -E ' (train|val)\.jsonl$' $M/SHA256SUMS | sed "s|  |  $M/|") || { note "ARRÊT : mélange modifié"; exit 1; }
grep -q '"rejected": \[\]' $M/leak.log || { note "ARRÊT : cas du banc dans le mélange"; exit 1; }
[ -n "${1:-}" ] && while kill -0 $1 2>/dev/null; do sleep 60; done
for s in 42 7; do
  O=$W/sft-s$s
  [ -f $O/adapter/adapter_model.safetensors ] && continue
  while [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ] \
     || [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -lt 10500 ]; do sleep 30; done
  note "SFT départ s$s"
  cd $R/bench/matrix/finetune/gemma && PYTHONPATH=$R/src nice -n 19 \
    $T/ft/venv/bin/python train_sft_gemma.py --model $T/gemma/qat --train $M/train.jsonl --val $M/val.jsonl --out $O \
    --generic-prompt --batch 16 --micro 4 --maxlen 2048 --lr 1e-4 --epochs 2 --evals-per-epoch 4 --patience 3 --seed $s \
    > $W/logs/sft-s$s.log 2>&1
  rc=$?; cd $W
  note "SFT s$s rc=$rc $(tail -1 $W/logs/sft-s$s.log | cut -c1-160)"
  [ $rc = 0 ] || exit 1
  note "adaptateur s$s $(sha256sum $O/adapter/adapter_model.safetensors | cut -c1-16)"
done
note "FIN"
