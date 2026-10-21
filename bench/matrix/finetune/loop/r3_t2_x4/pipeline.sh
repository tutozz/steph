#!/bin/bash
# R3-T2 partie 1 : recette R1 (v1.0) inchangée sur mix-x4, Granite H 350M depuis P17 fusionné (base de R1), RTX 3080.
# run_k3.sh de R1 (md5 égal) : SFT 4 graines -> soupe -> paires DPO (sorties SFT jugées par A7) + 71 paires P17 -> DPO 4 graines,
# puis fusion à l'échelle SFT 0,7 comme R1 (r1-i1-l07 = v1.0), GGUF Q4_K_M.
set -u
W=/root/steph-ft/loop/r3t2p1; R=$W/repo; F=$R/bench/matrix/finetune; B=/root/steph-ft/llama.cpp/build/bin
PY=/root/steph-ft/venv/bin/python; BASE=/root/steph-ft/r1/base-p17; V=x4
export K3=$W TAG=r3p1 MIX=$W/mix-x4 F16_DIR=/tmp SFT_LR=2e-4 EXTRA_PAIRS=/root/steph-ft/p17/pairs-train.jsonl
S=$F/pref/run_k3.sh
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
cd $W
bash $S sft $V $BASE && bash $S soup $V $BASE && bash $S pairs $V $BASE && bash $S dpo $V $BASE || { note "CHAÎNE KO"; exit 1; }
ad() { for s in 42 7 123 2024; do echo -n "$W/$V/$1-s$s/adapter "; done; }
N=r3p1-x4-l07; G=$W/gguf/$N-Q4_K_M.gguf
if [ ! -f $G ]; then
  $PY $F/pref/merge_pref.py --base $BASE --out /tmp/$N --sft $(ad sft) --pref $(ad dpo) --sft-scale 0.7 \
    > $W/logs/$N-merge.log 2>&1 || { note "FUSION KO $N"; exit 1; }
  cp $BASE/config.json /tmp/$N/config.json
  $PY /root/steph-ft/llama.cpp/convert_hf_to_gguf.py /tmp/$N --outfile /tmp/$N-f16.gguf --outtype f16 > $W/logs/$N-conv.log 2>&1 \
    && $B/llama-quantize /tmp/$N-f16.gguf $G Q4_K_M > $W/logs/$N-q.log 2>&1 || { rm -rf /tmp/$N /tmp/$N-f16.gguf; note "GGUF KO $N"; exit 1; }
  rm -rf /tmp/$N /tmp/$N-f16.gguf
fi
note "PIPELINE $(sha256sum $G | cut -c1-16)"
