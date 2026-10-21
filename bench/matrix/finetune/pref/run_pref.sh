#!/bin/bash
# [WORK=.. DATA=.. SFT="a1 a2.." EVAL=0] run_pref.sh <variante> [args train_dpo...] : juge des sorties, paires, DPO 4 graines, soupe, GGUF Q4_K_M, banc + TermSpeak
set -u
P=${WORK:-/root/steph-ft/pref}; S=/root/steph-ft/soup; D=${DATA:-/root/steph-ft/data/mix-judged}; PY=/root/steph-ft/venv/bin/python
MODEL=$(cat /root/steph-ft/opt/model_granite.txt); V=$1; shift
SFT=${SFT:-"$S/runs/granite-s42/adapter $S/runs/granite-s123/adapter $S/adapters/granite-s7 $S/adapters/granite-s2024"}
export HF_HOME=/root/steph-ft/hf-cache HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd $P
if [ ! -f pairs-counts.json ]; then
  PYTHONPATH=/root/steph-ft/judge python3 judge_outputs.py --data $D --gen gen.jsonl --out verdicts.jsonl >> logs/judge2.log 2>&1 || { echo "JUGE KO" >> run.done; exit 1; }
  PYTHONPATH=/root/steph-ft/judge python3 build_pairs.py --data $D --gen gen.jsonl --verdicts verdicts.jsonl --out $P >> logs/pairs.log 2>&1 || { echo "PAIRES KO" >> run.done; exit 1; }
fi
[ -f judge-server.pid ] && kill $(cat judge-server.pid) 2>/dev/null && rm judge-server.pid && sleep 5
PREF=""
for sd in 42 7 123 2024; do
  R=runs/$V-s$sd
  [ -f $R/adapter/adapter_model.safetensors ] || nice -n 5 $PY train_dpo.py --model $MODEL --sft-adapters $SFT \
    --pairs pairs-train.jsonl --val-pairs pairs-val.jsonl --val $D/val.jsonl --out $R --seed $sd "$@" > logs/$V-s$sd.log 2>&1 \
    || { echo "DPO KO $V s$sd" >> run.done; exit 1; }
  PREF="$PREF $R/adapter"
done
N=$V-uniform; mkdir -p gguf
if [ ! -f gguf/$N-Q4_K_M.gguf ]; then
  nice -n 10 $PY merge_pref.py --base $MODEL --out merged-$N --sft $SFT --pref $PREF > logs/$N-merge.log 2>&1 || { echo "FUSION KO" >> run.done; exit 1; }
  $PY /root/steph-ft/llama.cpp/convert_hf_to_gguf.py merged-$N --outfile gguf/$N-f16.gguf --outtype f16 > logs/$N-conv.log 2>&1 || { echo "CONVERSION KO" >> run.done; exit 1; }
  /root/steph-ft/llama.cpp/build/bin/llama-quantize gguf/$N-f16.gguf gguf/$N-Q4_K_M.gguf Q4_K_M > logs/$N-q.log 2>&1 || { echo "QUANT KO" >> run.done; exit 1; }
  rm -rf merged-$N gguf/$N-f16.gguf
fi
[ "${EVAL:-1}" = 1 ] && bash $(dirname "$0")/run_eval.sh $P/gguf/$N-Q4_K_M.gguf $N-Q4_K_M >> logs/eval-$N.log 2>&1
echo "FINI $V" >> run.done
