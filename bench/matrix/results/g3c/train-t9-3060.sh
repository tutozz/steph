#!/bin/bash
# G3c-t9, réaffinage sur l'hôte de la 3060 après la mise à jour T9 : recette G3b exacte (comme train-3060.sh) sur `g3c/mix-t9`
# (final-t9 à la place de final-x4-l5, corrections T9, correctif de langue x2, étiquettes publiques G3c), graines 42 puis 7.
# Le SFT s42 de l'ancien mélange (x4-l5 plus public) est gardé comme point de comparaison : on attend la fin de son PID
# (son script parent, qui aurait enchaîné s7 sur l'ancien mélange, est arrêté) et on note son résultat à sa place.
#   train-t9-3060.sh <PID du SFT s42 de l'ancien mélange>
set -u
T=/mnt/backup-hdd/stephbench-tmp; G=$T/g3c; W=$G/train; R=$T/gemma/g3b/repo; M=$G/mix-t9
note() { echo "$(date '+%d %H:%M') $*" >> $W/run.done; }
cd $W
sha256sum -c --quiet <(sed "s|  |  $M/|" $M/SHA256SUMS) || { note "ARRÊT : mélange t9 modifié"; exit 1; }
grep -q '"rejected": \[\]' $M/leak.log || { note "ARRÊT : cas du banc dans le mélange t9"; exit 1; }
grep -q '^TOTAL : 0$' $M/pii.log || { note "ARRÊT : audit_pii du mélange t9"; exit 1; }
if [ -n "${1:-}" ]; then
  while kill -0 $1 2>/dev/null; do sleep 60; done
  if [ -f $W/sft-s42/adapter/adapter_model.safetensors ]; then
    note "SFT s42 rc=0 $(grep -v '^{' $W/logs/sft-s42.log | tail -1 | cut -c1-160)"
    note "adaptateur s42 $(sha256sum $W/sft-s42/adapter/adapter_model.safetensors | cut -c1-16)"
  else
    note "SFT s42 rc=1 $(tail -1 $W/logs/sft-s42.log | cut -c1-160)"
  fi
fi
for s in 42 7; do
  tag=t9s$s; O=$W/sft-$tag
  [ -f $O/adapter/adapter_model.safetensors ] && continue
  while [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ] \
     || [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -lt 10500 ]; do sleep 30; done
  note "SFT départ $tag"
  cd $R/bench/matrix/finetune/gemma && PYTHONPATH=$R/src nice -n 19 \
    $T/ft/venv/bin/python train_sft_gemma.py --model $T/gemma/qat --train $M/train.jsonl --val $M/val.jsonl --out $O \
    --generic-prompt --batch 16 --micro 4 --maxlen 2048 --lr 1e-4 --epochs 2 --evals-per-epoch 4 --patience 3 --seed $s \
    > $W/logs/sft-$tag.log 2>&1
  rc=$?; cd $W
  note "SFT $tag rc=$rc $(tail -1 $W/logs/sft-$tag.log | cut -c1-160)"
  [ $rc = 0 ] || exit 1
  note "adaptateur $tag $(sha256sum $O/adapter/adapter_model.safetensors | cut -c1-16)"
done
note "FIN t9"
