#!/bin/bash
# G4b : juge A7 (Qwen3.5 9B Q4_K_M 03b74727, judge_lib A7 et judge_x3.py de G3, 2 passes) sur la 3060 (la 3080 est prise par G5),
# banc v3 test aligné L5, cache de verdicts propre à G4b, contrôles 6/6 avant et après.
#   SEEDS="7" judge-3060.sh <modèle>... (graines 7 42 123 par défaut ; attend runs/<modèle>-test-b<graine>.json)
set -u
T=/mnt/backup-hdd/stephbench-tmp; J=$T/gemma/g4b/judge; C=$T/loop/r3t4/code; X=$T/gemma/g3/judge-test
B=/root/stephbench-matrix/bin/vulkan/llama-b11205; QWEN=$T/models/Qwen3.5-9B-Q4_K_M.gguf; P=8992
export JUDGE_PORT=$P LD_LIBRARY_PATH=$B PYTHONPATH=$C/judge:$X
cd $J; mkdir -p logs verdicts runs
note() { echo "$(date +%H:%M) $*" >> $J/run.done; }
while [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]; do sleep 5; done
nice -n 19 $B/llama-server -m $QWEN --host 127.0.0.1 --port $P -c 16384 -ngl 99 --parallel 4 --no-webui --jinja --reasoning-budget 0 > logs/qwen.log 2>&1 < /dev/null &
QP=$!
for i in $(seq 120); do curl -sf http://127.0.0.1:$P/health >/dev/null && break; sleep 2; done
note "juge $(sha256sum $QWEN | cut -c1-16)"
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json validate-pre.json > logs/validate-pre.log 2>&1; note "VALIDATION avant rc=$? $(tail -1 logs/validate-pre.log)"
for m in "$@"; do for sd in ${SEEDS:-7 42 123}; do
  r=$m-test-b$sd
  nice -n 19 python3 $X/judge_x3.py test.generic.json verdicts/inv-$r.json runs/$r.json --cache verdicts --threads 8 > logs/$r.log 2>&1
  note "JUGE $r rc=$? $(tail -1 logs/$r.log)"
done; done
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json validate-post.json > logs/validate-post.log 2>&1; note "VALIDATION après rc=$? $(tail -1 logs/validate-post.log)"
kill $QP
note "FIN"
