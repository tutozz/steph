#!/bin/bash
# G3 : LoRA SFT Gemma 4 E2B sur mix-x4r1 (même mix que R3-T3), prompt générique de production. $1 = graine.
set -eu
G=/mnt/backup-hdd/stephbench-tmp/gemma; F=$G/repo/bench/matrix/finetune/gemma; M=/mnt/backup-hdd/stephbench-tmp/loop/r3t3/work/mix-x4r1
cd $F && PYTHONPATH=$G/repo/src nice -n 19 /mnt/backup-hdd/stephbench-tmp/ft/venv/bin/python train_sft_gemma.py --model $G/qat \
  --train $M/train.jsonl --val $M/val.jsonl --out $G/g3/sft-s$1 --generic-prompt \
  --batch 16 --micro ${2:-4} --maxlen 2048 --lr 1e-4 --epochs 2 --evals-per-epoch 4 --patience 3 --seed $1
