#!/bin/bash
# G3 éval : juge A7 (Qwen3.5 9B Q4_K_M 03b74727, judge_lib A7 intact) sur la 3080 une fois les couloirs de génération finis.
# Réponses reaches_model du split test ; cache par (harnais, cas, réponse), avec les verdicts R2 du même harnais test.
#   judge.sh <run>:<harnais> ...
set -u
W=/root/steph-ft/g3/eval; J=$W/judge; P=8997
M=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf; SRV=/root/steph-ft/llama.cpp/build/bin/llama-server
T=$W/repo/bench/matrix/v3/tools
note() { echo "$(date +%T) $*" >> $J/judge.done; }
cd $J
note "ATTENTE fin des couloirs et carte libre"
until [ "$(grep -c "LANE .* FIN" $W/logs/done.log)" -ge 3 ] && [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge 8000 ]; do sleep 60; done
nice -n 5 $SRV -m $M --host 127.0.0.1 --port $P -c 16384 --parallel 4 -ngl 99 --jinja --no-webui --reasoning-budget 0 > srv.log 2>&1 < /dev/null &
echo $! > srv.pid
for i in $(seq 180); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
export JUDGE_PORT=$P PYTHONPATH=$J/jl:$T
python3 j.py $T/judge_validate_v3.py run controls.json validate-pre.json > logs/validate-pre.log 2>&1; note "VALIDATION avant rc=$? $(tail -1 logs/validate-pre.log)"
for mh in "$@"; do
  m=${mh%%:*}; h=${mh##*:}
  python3 judge_x3.py $W/harness/$h.json $W/verdicts/inv-$m.json $W/runs/$m.json --cache cache --threads 8 > logs/$m.log 2>&1
  note "JUGE $m rc=$? $(tail -1 logs/$m.log)"
  ln -sf $W/verdicts/inv-$m.json cache/inv-g3-$m.json
done
python3 j.py $T/judge_validate_v3.py run controls.json validate-post.json > logs/validate-post.log 2>&1; note "VALIDATION après rc=$? $(tail -1 logs/validate-post.log)"
kill $(cat srv.pid); rm -f srv.pid
note "FIN"
