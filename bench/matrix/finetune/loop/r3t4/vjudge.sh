#!/bin/bash
# Juge A7 des runs du banc (réponses au banc dev, aucun texte de corpus) sur la 3060 : validation, jugement, validation, fusion.
#   vjudge.sh <sortie> <run...>
set -u
W=/mnt/backup-hdd/stephbench-tmp/loop/r3t4; C=$W/code
B=/root/stephbench-matrix/bin/vulkan/llama-b11205/llama-server; QWEN=/mnt/backup-hdd/stephbench-tmp/models/Qwen3.5-9B-Q4_K_M.gguf
export JUDGE_PORT=8984 PYTHONPATH=$C/judge:$C
cd $W; mkdir -p logs judge runs
note() { echo "$(date +%H:%M) $*" >> $W/vjudge.done; }
OUT=$1; shift
nice -n 19 $B -m $QWEN --host 127.0.0.1 --port $JUDGE_PORT -c 16384 -ngl 99 --parallel 4 --no-webui --jinja \
  --reasoning-budget 0 > logs/vqwen-$OUT.log 2>&1 < /dev/null &
QP=$!
for i in $(seq 120); do curl -sf http://127.0.0.1:$JUDGE_PORT/health > /dev/null && break; sleep 2; done
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/validate-$OUT-pre.json > logs/v-$OUT-pre.log 2>&1
rc=$?; note "VALIDATION $OUT avant rc=$rc"
if [ $rc = 0 ]; then
  nice -n 19 python3 $C/j.py $C/judge_bench_fast.py judge --harness $C/dev.json --cache judge/bench-cache --threads 8 --shard ${SHARD:-0} --nshards ${NSH:-1} "$@" > logs/$OUT.log 2>&1 || note "JUGE KO $OUT"
  python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/validate-$OUT-post.json > logs/v-$OUT-post.log 2>&1
  note "VALIDATION $OUT après rc=$?"
fi
kill $QP; for i in $(seq 30); do kill -0 $QP 2>/dev/null || break; sleep 1; done; kill -9 $QP 2>/dev/null  # arrêt Vulkan parfois bloqué
python3 $C/judge_bench_fast.py merge --harness $C/dev.json --cache judge/bench-cache --out judge/$OUT.json "$@" >> logs/$OUT.log 2>&1
note "JUGE BANC $OUT $(tail -1 logs/$OUT.log)"
