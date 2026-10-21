#!/bin/bash
# G4 : juge A7 (Qwen3.5 9B Q4_K_M 03b74727, 2 passes) sur les réponses reaches_model des variantes, banc v3 test.
#   Même dossier que G3 : cache par (harnais, cas, réponse) partagé avec les verdicts G3.
#   judge-g4.sh <run sans .json>... : ordre de priorité ; juge le premier run présent et non jugé, jusqu'à épuisement de la liste.
set -u
J=/mnt/backup-hdd/stephbench-tmp/gemma/g3/judge-test; C=/mnt/backup-hdd/stephbench-tmp/loop/r3t4/code
B=/root/stephbench-matrix/bin/vulkan/llama-b11205; QWEN=/mnt/backup-hdd/stephbench-tmp/models/Qwen3.5-9B-Q4_K_M.gguf
export JUDGE_PORT=8988 LD_LIBRARY_PATH=$B PYTHONPATH=$C/judge:$J
cd $J
note() { echo "$(date +%H:%M) $*" >> $J/run-g4.done; }
while :; do f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l); [ "$f" -ge 9000 ] && [ "$n" -eq 0 ] && break; sleep 600; done
nice -n 19 $B/llama-server -m $QWEN --host 127.0.0.1 --port $JUDGE_PORT -c 16384 -ngl 99 --parallel 4 --no-webui --jinja --reasoning-budget 0 > logs/qwen-g4.log 2>&1 < /dev/null &
QP=$!
for i in $(seq 120); do curl -sf http://127.0.0.1:$JUDGE_PORT/health >/dev/null && break; sleep 2; done
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json validate-g4-pre.json > logs/validate-g4-pre.log 2>&1; note "VALIDATION avant rc=$? $(tail -1 logs/validate-g4-pre.log)"
while :; do
  left=0; did=0
  for m in "$@"; do
    [ -f logs/$m.judged ] && continue
    left=1; [ -f runs/$m.json ] || continue
    nice -n 19 python3 judge_x3.py test.generic.json verdicts/inv-$m.json runs/$m.json --cache verdicts --threads 8 > logs/$m.log 2>&1
    rc=$?; note "JUGE $m rc=$rc $(tail -1 logs/$m.log)"; [ $rc = 0 ] && touch logs/$m.judged; did=1; break
  done
  [ $left = 0 ] && break
  [ $did = 0 ] && sleep 60
done
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json validate-g4-post.json > logs/validate-g4-post.log 2>&1; note "VALIDATION après rc=$? $(tail -1 logs/validate-g4-post.log)"
kill $QP
