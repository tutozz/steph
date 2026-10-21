#!/bin/bash
# G3 éval : formulation à l oral (judge_style_v3.py, Qwen3.5 27B Q4_K_M, verdict global), split test, graine 7,
# 240 paires différentes tirées par hachage (style_sample.py, même tirage que R2). Un seul 27B, cœurs 0-31, 64 Go, nice 19, aucune VM.
#   style.sh <x> <y> [<x> <y> ...] ; runs/<m>-test-b7.json relayés depuis la 3080
set -u
W=/root/steph-ft/g3/eval; T=$W/repo/bench/matrix/v3/tools; P=8996; N=${N:-240}
M=/root/steph-ft/x4a/models/Qwen3.5-27B-Q4_K_M.gguf; SRV=/root/steph-ft/llama/llama-b11205/llama-server
note() { echo "$(date +%T) $*" >> $W/style.done; }
n27() { ps -C llama-server -o args= | grep -c "27B"; }
cd $W
note "ATTENTE aucun autre 27B et 40 Go libres"
until [ "$(n27)" -eq 0 ] && [ "$(awk "/MemAvailable/ {print int(\$2/1048576)}" /proc/meminfo)" -ge 40 ]; do sleep 60; done
export LD_LIBRARY_PATH=/root/steph-ft/llama/llama-b11205:/root/steph-ft/vendor/lib
systemd-run --scope -q -p AllowedCPUs=0-31 -p MemoryMax=64G nice -n 19 $SRV -m $M --host 127.0.0.1 --port $P -c 16384 -t 32 \
  --parallel 2 --jinja --no-webui -ub 512 > logs/srv27.log 2>&1 < /dev/null &
for i in $(seq 300); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:$P/health > /dev/null || { note "27B KO"; exit 1; }
note "27B PRÊT"
while [ $# -ge 2 ]; do
  x=$1; y=$2; shift 2
  until [ -f runs/$x-test-b7.json ] && [ -f runs/$y-test-b7.json ]; do sleep 60; done
  python3 $T/style_sample.py runs/$x-test-b7.json runs/$y-test-b7.json $N runs/$x-vs-$y-x.json runs/$x-vs-$y-y.json > style-sample-$x-vs-$y.json
  note "PAIRES $x contre $y $(cat style-sample-$x-vs-$y.json)"
  python3 $T/judge_style_v3.py run $W/repo/bench/matrix/v3/harness/test.generic.json style-$x-vs-$y.json \
    --a runs/$x-vs-$y-x.json --b runs/$x-vs-$y-y.json --ports $P,$P > logs/style-$x-vs-$y.log 2>&1
  note "STYLE $x contre $y rc=$?"
done
kill $(ps -C llama-server -o pid=,args= | awk -v p="--port $P" "index(\$0,p) {print \$1}")
note "FIN"
