#!/bin/bash
# feature_run_r1.sh <étiquette=gguf>... : sorties sur la validation du mix R1 (3 graines), juge A7 2 passes, comptes par source.
set -u
R=/root/steph-ft/r1; F=$R/repo/bench/matrix/finetune; B=/root/steph-ft/llama.cpp/build/bin; D=$R/valcheck
note() { echo "$(date +%H:%M) $*" >> $R/run.done; }
mkdir -p $D; : > $D/train.jsonl; cp $R/mix-i1/val.jsonl $D/val.jsonl
for spec in "$@"; do
  L=${spec%%=*}; G=${spec#*=}
  $B/llama-server -m $G --host 127.0.0.1 --port 8952 -c 16384 -ngl 99 --parallel 8 --no-webui --jinja --reasoning-budget 0 \
    > $R/logs/valcheck-$L.log 2>&1 < /dev/null &
  SP=$!
  for i in $(seq 60); do curl -sf http://127.0.0.1:8952/health >/dev/null && break; sleep 2; done
  python3 $F/pref/gen_outputs.py --data $D --port 8952 --out $D/gen-$L.jsonl --seeds 42 7 123 --repeat-penalty 1.0 \
    --max-tokens 160 --parallel 8 > $R/logs/valcheck-gen-$L.log 2>&1
  kill $SP; sleep 3
done
$B/llama-server -m /root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf --host 127.0.0.1 --port 8931 -ngl 99 -c 16384 \
  --parallel 4 --no-webui --jinja --reasoning-budget 0 > $R/logs/qwen-valcheck.log 2>&1 < /dev/null &
QP=$!
for i in $(seq 120); do curl -sf http://127.0.0.1:8931/health >/dev/null && break; sleep 2; done
for spec in "$@"; do
  L=${spec%%=*}
  PYTHONPATH=/root/steph-ft/judge:$F/pref python3 $F/pref/judge_outputs.py --data $D --gen $D/gen-$L.jsonl \
    --out $D/verdicts-$L.jsonl --parallel 4 > $R/logs/valcheck-judge-$L.log 2>&1
  PYTHONPATH=$R/repo/src:/root/steph-ft/judge python3 $F/pref/feature_check_r1.py $D $D/gen-$L.jsonl $D/verdicts-$L.jsonl > $R/eval/valcheck-$L.json
  note "VALCHECK $L"
done
kill $QP
