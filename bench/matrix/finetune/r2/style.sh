#!/bin/bash
# R2 : formulation à l'oral (judge_style_v3.py, Qwen3.5 27B Q4_K_M, verdict global seul), R2 (x) contre v1.0 (y),
# split test, graine 7, 240 paires différentes tirées par hachage (style_sample.py). CPU xeon : un seul 27B,
# lancé à côté d'au plus deux 27B de la boucle (OOM constaté à quatre), 40 Go disponibles exigés, cœurs 0-31, 64 Go au plus, nice 19 ; aucune VM touchée.
set -u
W=/root/steph-ft/r2; T=$W/repo/bench/matrix/v3/tools; P=8990; N=${N:-240}
M=/root/steph-ft/x4a/models/Qwen3.5-27B-Q4_K_M.gguf; SRV=/root/steph-ft/llama/llama-b11205/llama-server
note() { echo "$(date +%T) $*" >> $W/style.done; }
n27() { ps -C llama-server -o args= | grep -c "27B"; }
cd $W
note "ATTENTE au plus deux autres 27B et 40 Go libres"
until [ "$(n27)" -le 2 ] && [ "$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)" -ge 40 ]; do sleep 60; done
python3 $T/style_sample.py runs/r2-test-b7.json runs/v10-test-b7.json $N runs/r2-style.json runs/v10-style.json > style-sample.json
export LD_LIBRARY_PATH=/root/steph-ft/llama/llama-b11205:/root/steph-ft/vendor/lib
systemd-run --scope -q -p AllowedCPUs=0-31 -p MemoryMax=64G nice -n 19 $SRV -m $M --host 127.0.0.1 --port $P -c 8192 -t 16 \
  --parallel 1 --jinja --no-webui -ub 512 > srv27.log 2>&1 < /dev/null &
for i in $(seq 300); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:$P/health > /dev/null || { note "27B KO"; exit 1; }
note "27B PRÊT $(cat style-sample.json)"
python3 $T/judge_style_v3.py run $W/repo/bench/matrix/v3/harness/test.json style-r2-v10.json \
  --a runs/r2-style.json --b runs/v10-style.json --ports $P > style.log 2>&1
note "STYLE rc=$?"
kill $(ps -C llama-server -o pid=,args= | awk -v p="--port $P" 'index($0,p) {print $1}')
note "FIN"
