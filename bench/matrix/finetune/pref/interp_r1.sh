#!/bin/bash
# R1, itération 2 : P17 + lambda * delta SFT R1 + delta DPO R1 (interpolation vers P17), puis bancs et juges.
#   interp_r1.sh <variante> <lambda...>   ex. interp_r1.sh i1 0.5 0.7
set -u
V=$1; shift
R=/root/steph-ft/r1; F=$R/repo/bench/matrix/finetune; B=/root/steph-ft/llama.cpp/build/bin; PY=/root/steph-ft/venv/bin/python
export K3=$R
note() { echo "$(date +%H:%M) $*" >> $R/run.done; }
ad() { for s in 42 7 123 2024; do echo -n "$R/$V/$1-s$s/adapter "; done; }
LABELS=""
for L in "$@"; do
  N=r1-$V-l${L/./}
  G=$R/gguf/$N-Q4_K_M.gguf
  if [ ! -f $G ]; then
    $PY $F/pref/merge_pref.py --base $R/base-p17 --out /tmp/$N --sft $(ad sft) --pref $(ad dpo) --sft-scale $L \
      > $R/logs/$N-merge.log 2>&1 || { note "FUSION KO $N"; exit 1; }
    cp $R/base-p17/config.json /tmp/$N/config.json
    $PY /root/steph-ft/llama.cpp/convert_hf_to_gguf.py /tmp/$N --outfile /tmp/$N-f16.gguf --outtype f16 > $R/logs/$N-conv.log 2>&1 \
      && $B/llama-quantize /tmp/$N-f16.gguf $G Q4_K_M > $R/logs/$N-q.log 2>&1 || { note "GGUF KO $N"; exit 1; }
    rm -rf /tmp/$N /tmp/$N-f16.gguf
  fi
  bash $F/pref/run_eval_k3.sh $G $N
  LABELS="$LABELS $N"
done
bash $F/pref/judge_r1.sh $LABELS
note "INTERP $V$LABELS"
