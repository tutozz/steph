#!/bin/bash
# G5c : formulation à l'oral (judge_style_v3.py, Qwen3.5 27B Q4_K_M, verdict global) sur xeon en CPU, cœurs 0-31,
# 48 Go au plus, nice 19, un seul 27B, aucune VM touchée ; harnais affiné L5 test.json (705fdcb9), graine 7, 240 paires
# par hachage (style_sample.py de R2). Un slot et --cache-ram 0 (G3b : --parallel 2 fait suivre l'ordre de présentation).
# Contrôles plantés de X5 avant et après les paires.
#   style_xeon.sh <x> <y> [<x> <y> ...] ; runs/<m>-test-b7.json relayés depuis la 3080
set -u
W=/root/steph-ft/g5c; R=$W/repo/bench/matrix; T=$R/v3/tools; P=8996; N=${N:-240}
M=/root/steph-ft/x4a/models/Qwen3.5-27B-Q4_K_M.gguf; SRV=/root/steph-ft/llama/llama-b11205/llama-server
H=$R/v3/harness/test.json
note() { echo "$(date +%T) $*" >> $W/style.done; }
cd $W; mkdir -p runs style logs
note "harnais $(sha256sum $H | cut -c1-16) ; 27B $(sha256sum $M | cut -c1-16)"
until [ "$(ps -C llama-server -o args= | grep -c 27B)" -eq 0 ] && \
      [ "$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)" -ge 40 ]; do sleep 60; done
export LD_LIBRARY_PATH=/root/steph-ft/llama/llama-b11205:/root/steph-ft/vendor/lib
systemd-run --scope -q -p AllowedCPUs=0-31 -p MemoryMax=48G nice -n 19 $SRV -m $M --host 127.0.0.1 --port $P -c 8192 -t 32 \
  --parallel 1 --cache-ram 0 --jinja --no-webui -ub 512 > logs/srv27.log 2>&1 < /dev/null &
for i in $(seq 300); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:$P/health > /dev/null || { note "27B KO"; exit 1; }
note "27B PRÊT"
controls() {
  [ -f style/controls-$1.json ] && return 0
  python3 $T/judge_style_v3.py controls $R/v3/x5/controls.jsonl style/controls-$1.json --ports $P > logs/controls-$1.log 2>&1
  note "CONTRÔLES $1 rc=$? $(tr -d '\n ' < logs/controls-$1.log | tail -c 200)"
}
controls pre
while [ $# -ge 2 ]; do
  x=$1; y=$2; shift 2
  [ -f style/style-$x-vs-$y.json ] && continue
  until [ -f runs/$x-test-b7.json ] && [ -f runs/$y-test-b7.json ]; do sleep 60; done
  python3 $R/finetune/r2/style_sample.py runs/$x-test-b7.json runs/$y-test-b7.json $N style/$x-vs-$y-x.json style/$x-vs-$y-y.json \
    > style/sample-$x-vs-$y.json
  note "PAIRES $x contre $y $(cat style/sample-$x-vs-$y.json)"
  python3 $T/judge_style_v3.py run $H style/style-$x-vs-$y.json --a style/$x-vs-$y-x.json --b style/$x-vs-$y-y.json \
    --ports $P > logs/style-$x-vs-$y.log 2>&1
  note "STYLE $x contre $y rc=$?"
done
controls post
kill $(ps -C llama-server -o pid=,args= | awk -v p="--port $P" 'index($0,p) {print $1}')
note "FIN"
