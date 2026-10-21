#!/bin/bash
# G3 : LoRA SFT Gemma 4 E2B sur mix-x4r1 (sha256 89d793c8, identique à la 3060), prompt générique ; base en RAM (/dev/shm, disque plein). $1 = graine, $2 = micro.
set -eu
W=/root/steph-ft/g3; F=$W/repo/bench/matrix/finetune/gemma
cd $F && PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True HF_HOME=/dev/shm/g3-hf PYTHONPATH=$W/repo/src nice -n 19 /root/steph-ft/venv/bin/python train_sft_gemma.py --model /dev/shm/g3-qat \
  --train $W/mix-x4r1/train.jsonl --val $W/mix-x4r1/val.jsonl --out $W/sft-s$1 --generic-prompt \
  --batch 16 --micro ${2:-2} --maxlen 2048 --lr 1e-4 --epochs 2 --evals-per-epoch 4 --patience 3 --seed $1
