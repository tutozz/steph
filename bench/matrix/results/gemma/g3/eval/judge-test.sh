#!/bin/bash
# G3 éval : juge A7 (Qwen3.5 9B Q4_K_M 03b74727, 2 passes) sur les réponses reaches_model du banc v3 test, cache par (harnais, cas, réponse).
#   judge-test.sh <étiquette:harnais> ... ; runs/<étiquette>.json relayés depuis la 3080
set -u
J=/mnt/backup-hdd/stephbench-tmp/gemma/g3/judge-test; C=/mnt/backup-hdd/stephbench-tmp/loop/r3t4/code
B=/root/stephbench-matrix/bin/vulkan/llama-b11205; QWEN=/mnt/backup-hdd/stephbench-tmp/models/Qwen3.5-9B-Q4_K_M.gguf
export JUDGE_PORT=8988 LD_LIBRARY_PATH=$B PYTHONPATH=$C/judge:$J
cd $J
note() { echo "$(date +%H:%M) $*" >> $J/run.done; }
while :; do f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l); [ "$f" -ge 9000 ] && [ "$n" -eq 0 ] && break; sleep 600; done
nice -n 19 $B/llama-server -m $QWEN --host 127.0.0.1 --port $JUDGE_PORT -c 16384 -ngl 99 --parallel 4 --no-webui --jinja --reasoning-budget 0 > logs/qwen.log 2>&1 < /dev/null &
QP=$!
for i in $(seq 120); do curl -sf http://127.0.0.1:$JUDGE_PORT/health >/dev/null && break; sleep 2; done
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json validate-pre.json > logs/validate-pre.log 2>&1; note "VALIDATION avant rc=$? $(tail -1 logs/validate-pre.log)"
for mh in "$@"; do
  m=${mh%%:*}; h=${mh##*:}
  until [ -f runs/$m.json ]; do sleep 60; done
  nice -n 19 python3 judge_x3.py $h.json verdicts/inv-$m.json runs/$m.json --cache verdicts --threads 8 > logs/$m.log 2>&1
  note "JUGE $m rc=$? $(tail -1 logs/$m.log)"
done
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json validate-post.json > logs/validate-post.log 2>&1; note "VALIDATION après rc=$? $(tail -1 logs/validate-post.log)"
kill $QP
