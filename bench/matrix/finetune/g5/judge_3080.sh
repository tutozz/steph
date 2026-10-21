#!/bin/bash
# G5 : juge A7 (Qwen3.5 9B Q4_K_M 03b74727, judge_lib A7, judge_x3.py, 2 passes) sur la 3080, contrôles 6/6 FR et EN
# avant et après ; une graine entière sur la même carte. Juge arrêté par son PID.
#   judge_3080.sh <dev|test> <modèle>:<graine> ...
set -u
S=$1; shift
K=/root/steph-ft/g5; J=$K/judge; T=$K/repo/bench/matrix/v3/tools; P=8932
M=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf; SRV=/root/steph-ft/llama.cpp/build/bin/llama-server
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
cd $J; mkdir -p $K/verdicts
until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge 7000 ]; do sleep 60; done
nice -n 5 $SRV -m $M --host 127.0.0.1 --port $P -c 32768 --parallel 8 -ngl 99 --jinja --no-webui --reasoning-budget 0 \
  > $K/logs/qwen-$P.log 2>&1 < /dev/null &
SP=$!
for i in $(seq 180); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
export JUDGE_PORT=$P PYTHONPATH=$J/jl:$T
tag=$S-$(date +%H%M)
note "JUGE 3080 $(sha256sum $M | cut -c1-16) PID $SP"
python3 j.py $T/judge_validate_v3.py run controls.json $K/verdicts/validate-pre-$tag.json > $K/logs/validate-pre-$tag.log 2>&1
note "VALIDATION 3080 avant rc=$? $(tail -1 $K/logs/validate-pre-$tag.log)"
for ms in "$@"; do
  r=${ms%%:*}-$S-b${ms##*:}
  until [ -f $K/runs/$r.json ]; do sleep 60; done
  for try in 1 2 3; do
    kill -0 $SP 2>/dev/null || { note "ARRÊT : juge $SP mort"; exit 1; }
    nice -n 5 python3 judge_x3.py $K/repo/bench/matrix/v3/harness/$S.json $K/verdicts/inv-$r.json $K/runs/$r.json \
      --cache $K/verdicts --threads 8 > $K/logs/j-$r.log 2>&1
    note "JUGE $r essai $try rc=$? $(tail -1 $K/logs/j-$r.log)"
    tail -1 $K/logs/j-$r.log | grep -q '"erreur": 0' && break
  done
done
python3 j.py $T/judge_validate_v3.py run controls.json $K/verdicts/validate-post-$tag.json > $K/logs/validate-post-$tag.log 2>&1
note "VALIDATION 3080 après rc=$? $(tail -1 $K/logs/validate-post-$tag.log)"
kill $SP; note "FIN juge 3080 $S"
