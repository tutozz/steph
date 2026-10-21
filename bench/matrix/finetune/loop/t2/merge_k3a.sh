#!/bin/bash
# Reconstruit les poids fusionnés de K3-a (base P17 + moyennes des adaptateurs SFT et DPO), puis GGUF pour comparaison au GGUF d'origine
set -eu
T=/root/steph-ft/loop/t2; PY=/root/steph-ft/venv/bin/python; A=$T/k3a-adapters
cd $T
nice -n 10 $PY repo/pref/merge_pref.py --base /root/steph-ft/r1/base-p17 --out $T/k3a-merged \
  --sft $A/sft-s42/adapter $A/sft-s7/adapter $A/sft-s123/adapter $A/sft-s2024/adapter \
  --pref $A/dpo-s42/adapter $A/dpo-s7/adapter $A/dpo-s123/adapter $A/dpo-s2024/adapter
cp /root/steph-ft/r1/base-p17/config.json $T/k3a-merged/config.json
nice -n 10 $PY /root/steph-ft/llama/llama.cpp-src/convert_hf_to_gguf.py $T/k3a-merged --outfile $T/k3a-f16.gguf --outtype f16 > logs/k3a-conv.log 2>&1
LD_LIBRARY_PATH=/root/steph-ft/llama/cpu /root/steph-ft/llama/cpu/llama-quantize $T/k3a-f16.gguf $T/k3a-recon-Q4_K_M.gguf Q4_K_M > logs/k3a-q.log 2>&1
rm $T/k3a-f16.gguf
md5sum $T/k3a-recon-Q4_K_M.gguf $T/ref/k3-a-dpo-Q4_K_M.gguf
