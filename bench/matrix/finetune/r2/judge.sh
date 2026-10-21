#!/bin/bash
# R2 : juge A7 (Qwen3.5-9B Q4_K_M, judge_lib_a7 intact) sur la 3080, réponses reaches_model du split test,
# cache par (harnais, cas, réponse) partagé avec les verdicts X3 (harnais test identique à 145c373).
# Contrôles C1-C6 FR et 6 EN avant et après. Attend 6,5 Go libres, sans interrompre personne.
#   judge.sh <graine> <étiquette> [...]
set -u
W=/root/steph-ft/r2; J=$W/judge; P=8995; sd=$1; shift
M=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf; SRV=/root/steph-ft/llama.cpp/build/bin/llama-server
H=$W/repo/bench/matrix/v3/harness/test.json; T=$W/repo/bench/matrix/v3/tools
note() { echo "$(date +%T) $*" >> $J/judge.done; }
free_mib() { nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits; }
cd $J
note "ATTENTE carte"
until [ "$(free_mib)" -ge 6500 ]; do sleep 60; done
nice -n 5 $SRV -m $M --host 127.0.0.1 --port $P -c 16384 --parallel 4 -ngl 99 --jinja --no-webui > $J/srv.log 2>&1 < /dev/null &
echo $! > $J/srv.pid
for i in $(seq 180); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
export JUDGE_PORT=$P PYTHONPATH=$J/jl:$T
python3 j.py $T/judge_validate_v3.py run controls.json validate-before.json > validate-before.log 2>&1 \
  && note "CONTRÔLES AVANT OK" || { note "CONTRÔLES AVANT KO"; kill $(cat srv.pid); exit 1; }
for m in "$@"; do
  python3 judge_x3.py $H verdicts/inv-$m-test-b$sd.json $W/runs/$m-test-b$sd.json --cache verdicts --threads 4 \
    >> logs-$m-b$sd.log 2>&1
  note "$m b$sd rc=$?"
done
python3 j.py $T/judge_validate_v3.py run controls.json validate-after-b$sd.json > validate-after-b$sd.log 2>&1 \
  && note "CONTRÔLES APRÈS OK" || note "CONTRÔLES APRÈS KO"
kill $(cat srv.pid); rm -f srv.pid
note "FIN b$sd"
