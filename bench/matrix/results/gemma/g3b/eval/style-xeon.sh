#!/bin/bash
# G3b éval : formulation à l'oral (judge_style_v3.py, Qwen3.5 27B Q4_K_M 84b5f7f1, verdict global) sur xeon en CPU,
# cœurs 0-31, 64 Go, nice 19, aucune VM touchée ; harnais générique L5 (8d90a662), graine 7, 240 paires par hachage
# (style_sample.py de R2). Contrôles plantés de X5 d'abord (revalidation), puis les paires.
# Un seul slot et --cache-ram 0 : en CPU avec --parallel 2, le juge a suivi l'ordre de présentation (4 contrôles sur 60, biais 86,6 %).
#   style-xeon.sh <x> <y> [<x> <y> ...] ; runs/<m>-test-b7.json relayés depuis la 3080
set -u
W=/root/steph-ft/g3b; R=$W/repo/bench/matrix; T=$R/v3/tools; P=8997; N=${N:-240}
M=/root/steph-ft/x4a/models/Qwen3.5-27B-Q4_K_M.gguf; SRV=/root/steph-ft/llama/llama-b11205/llama-server
note() { echo "$(date +%T) $*" >> $W/style.done; }
cd $W; mkdir -p runs style logs
[ -f harness-test.generic.json ] || (cd $T && python3 generic_harness.py test $W/harness-test.generic.json)
note "harnais $(sha256sum harness-test.generic.json | cut -c1-16) ; 27B $(sha256sum $M | cut -c1-16)"
until [ "$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)" -ge 40 ]; do sleep 60; done
export LD_LIBRARY_PATH=/root/steph-ft/llama/llama-b11205:/root/steph-ft/vendor/lib
systemd-run --scope -q -p AllowedCPUs=0-31 -p MemoryMax=64G nice -n 19 $SRV -m $M --host 127.0.0.1 --port $P -c 8192 -t 32 \
  --parallel 1 --cache-ram 0 --jinja --no-webui -ub 512 > logs/srv27.log 2>&1 < /dev/null &
for i in $(seq 300); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:$P/health > /dev/null || { note "27B KO"; exit 1; }
note "27B PRÊT"
[ -f style/controls.json ] || { python3 $T/judge_style_v3.py controls $R/v3/x5/controls.jsonl style/controls.json --ports $P,$P > logs/controls.log 2>&1; note "CONTRÔLES rc=$? $(tail -1 logs/controls.log)"; }
while [ $# -ge 2 ]; do
  x=$1; y=$2; shift 2
  until [ -f runs/$x-test-b7.json ] && [ -f runs/$y-test-b7.json ]; do sleep 60; done
  python3 $R/finetune/r2/style_sample.py runs/$x-test-b7.json runs/$y-test-b7.json $N style/$x-vs-$y-x.json style/$x-vs-$y-y.json > style/sample-$x-vs-$y.json
  note "PAIRES $x contre $y $(cat style/sample-$x-vs-$y.json)"
  python3 $T/judge_style_v3.py run $W/harness-test.generic.json style/style-$x-vs-$y.json \
    --a style/$x-vs-$y-x.json --b style/$x-vs-$y-y.json --ports $P,$P > logs/style-$x-vs-$y.log 2>&1
  note "STYLE $x contre $y rc=$?"
done
kill $(ps -C llama-server -o pid=,args= | awk -v p="--port $P" 'index($0,p) {print $1}')
note "FIN"
