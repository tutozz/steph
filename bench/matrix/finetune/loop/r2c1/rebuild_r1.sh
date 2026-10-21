#!/bin/bash
# R2-C1 : reconstruit les poids HF de R1 v1.0 (P17 + 0,7 x delta SFT i1 + delta DPO i1) et vérifie le GGUF.
set -eu
R=/root/steph-ft/r1; W=/root/steph-ft/loop/r2c1; PY=/root/steph-ft/venv/bin/python; B=/root/steph-ft/llama.cpp/build/bin
ad() { for s in 42 7 123 2024; do echo -n "$R/i1/$1-s$s/adapter "; done; }
[ -f $W/r1-hf/model.safetensors ] || nice -n 19 $PY $W/code/merge_pref.py --base $R/base-p17 --out $W/r1-hf --sft $(ad sft) --pref $(ad dpo) --sft-scale 0.7
cp $R/base-p17/config.json $W/r1-hf/config.json
nice -n 19 $PY /root/steph-ft/llama.cpp/convert_hf_to_gguf.py $W/r1-hf --outfile /tmp/r2c1-r1-f16.gguf --outtype f16 > $W/logs/r1-conv.log 2>&1
nice -n 19 $B/llama-quantize /tmp/r2c1-r1-f16.gguf /tmp/r2c1-r1-Q4_K_M.gguf Q4_K_M > $W/logs/r1-q.log 2>&1
rm /tmp/r2c1-r1-f16.gguf
sha256sum /tmp/r2c1-r1-Q4_K_M.gguf $R/gguf/steph-speak-granite-4.0-h-350M-dpo-v1.0-Q4_K_M.gguf
