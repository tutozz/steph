#!/bin/bash
# G3b éval : juge A7 (Qwen3.5 9B Q4_K_M 03b74727, 2 passes) sur les réponses reaches_model du banc v3 test aligné L5,
# cache propre à G3b (contexte L5), contrôles 6/6 avant et après. Runs relayés depuis l'A1000 (relay.sh).
#   judge-3060.sh <modèle>:<harnais test|test.generic> ... ; attend runs/<modèle>-test-b<graine>.json, graines 7 42 123
set -u
T=/mnt/backup-hdd/stephbench-tmp; J=$T/gemma/g3b/judge-test; C=$T/loop/r3t4/code; X=$T/gemma/g3/judge-test
B=/root/stephbench-matrix/bin/vulkan/llama-b11205; QWEN=$T/models/Qwen3.5-9B-Q4_K_M.gguf; P=8991
export JUDGE_PORT=$P LD_LIBRARY_PATH=$B PYTHONPATH=$C/judge:$X
cd $J; mkdir -p logs verdicts runs
note() { echo "$(date +%H:%M) $*" >> $J/run.done; }
until [ -f $T/gemma/g3b/sft-s42/adapter/adapter_model.safetensors ]; do sleep 120; done
while [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]; do sleep 5; done
nice -n 19 $B/llama-server -m $QWEN --host 127.0.0.1 --port $P -c 16384 -ngl 99 --parallel 4 --no-webui --jinja --reasoning-budget 0 > logs/qwen.log 2>&1 < /dev/null &
QP=$!
for i in $(seq 120); do curl -sf http://127.0.0.1:$P/health >/dev/null && break; sleep 2; done
note "juge $(sha256sum $QWEN | cut -c1-16)"
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json validate-pre.json > logs/validate-pre.log 2>&1; note "VALIDATION avant rc=$? $(tail -1 logs/validate-pre.log)"
todo=(); for mh in "$@"; do for sd in 7 42 123; do todo+=("${mh%%:*}-test-b$sd:${mh##*:}"); done; done
while [ ${#todo[@]} -gt 0 ]; do
  left=(); did=0
  for rh in "${todo[@]}"; do
    r=${rh%%:*}; h=${rh##*:}
    if [ $did = 0 ] && [ -f runs/$r.json ]; then
      nice -n 19 python3 $X/judge_x3.py $h.json verdicts/inv-$r.json runs/$r.json --cache verdicts --threads 8 > logs/$r.log 2>&1
      note "JUGE $r rc=$? $(tail -1 logs/$r.log)"; did=1
    else left+=("$rh"); fi
  done
  todo=("${left[@]}"); [ $did = 0 ] && sleep 60
done
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json validate-post.json > logs/validate-post.log 2>&1; note "VALIDATION après rc=$? $(tail -1 logs/validate-post.log)"
kill $QP
note "FIN"
