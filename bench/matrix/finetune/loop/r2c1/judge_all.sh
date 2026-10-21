#!/bin/bash
# R2-C1 : une seule session de juge A7 pour R1 et les variantes (graine 7), validation 6/6 avant et après.
#   judge_all.sh <sortie> <modèle...>
set -u
OUT=$1; shift
W=/root/steph-ft/loop/r2c1; C=$W/code; B=/root/steph-ft/llama.cpp/build/bin
export JUDGE_PORT=8981 PYTHONPATH=$C/judge:$C
cd $W
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
vram() { while :; do f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); [ "$f" -ge $1 ] && return 0; sleep 60; done; }
vram 7200
$B/llama-server -m /root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf --host 127.0.0.1 --port 8981 -c 32768 -ngl 99 --parallel 4 --no-webui --jinja --reasoning-budget 0 \
  > logs/qwen-final.log 2>&1 < /dev/null &
QP=$!
for i in $(seq 120); do curl -sf http://127.0.0.1:8981/health >/dev/null && break; sleep 2; done
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/$OUT-validate-pre.json > logs/$OUT-vpre.log 2>&1; note "VALIDATION $OUT avant rc=$?"
RUNS=""; for m in "$@"; do RUNS="$RUNS runs/$m-dev-b7.json"; done
python3 $C/j.py $C/judge_v3.py $C/dev.json judge/$OUT.json $RUNS --threads 4 > logs/$OUT.log 2>&1 || note "JUGE KO $OUT"
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/$OUT-validate-post.json > logs/$OUT-vpost.log 2>&1; note "VALIDATION $OUT après rc=$?"
kill $QP
note "JUGE $OUT $(tail -1 logs/$OUT.log)"
