#!/bin/bash
# G5 : contre-jugement 27B (Qwen3.5 27B Q4_K_M, judge_lib A7 intact, b1_judge.py ab du tour 3) des évaluations discordantes
# au 9B, sur xeon en CPU : cœurs 0-31, 48 Go au plus, nice 19, un seul 27B, aucune VM touchée ; contrôles 6/6 avant et après.
#   inv27_xeon.sh <v27.jsonl> <tasks.json>... ; une réponse commune à deux fichiers de tâches n'est jugée qu'une fois
set -u
W=/root/steph-ft/g5; B1=$W/repo/bench/matrix/results/finetune/loop/round-3/b1/b1_judge.py; P=8995
M=/root/steph-ft/x4a/models/Qwen3.5-27B-Q4_K_M.gguf; SRV=/root/steph-ft/llama/llama-b11205/llama-server
note() { echo "$(date +%T) $*" >> $W/inv27.done; }
cd $W; mkdir -p logs
until [ "$(ps -C llama-server -o args= | grep -c 27B)" -eq 0 ] && \
      [ "$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)" -ge 40 ]; do sleep 60; done
export LD_LIBRARY_PATH=/root/steph-ft/llama/llama-b11205:/root/steph-ft/vendor/lib PYTHONPATH=$W/jl
systemd-run --scope -q -p AllowedCPUs=0-31 -p MemoryMax=48G nice -n 19 $SRV -m $M --host 127.0.0.1 --port $P -c 16384 -t 32 \
  --parallel 2 --cache-ram 0 -n 768 --jinja --no-webui > logs/srv27-inv.log 2>&1 < /dev/null &
for i in $(seq 300); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:$P/health > /dev/null || { note "27B KO"; exit 1; }
note "27B PRÊT $(sha256sum $M | cut -c1-16)"
python3 $B1 validate $W/controls.json logs/val27-before.json --port $P --timeout 1800 > logs/val27-before.log 2>&1
note "CONTRÔLES AVANT rc=$? $(tail -1 logs/val27-before.log)"
OUT=$1; shift
for t in "$@"; do
  python3 $B1 ab $t $OUT --port $P --threads 2 --timeout 1800 > logs/inv27-$(basename $t .json).log 2>&1
  note "JUGE27 $t rc=$? $(tail -1 logs/inv27-$(basename $t .json).log)"
done
python3 $B1 validate $W/controls.json logs/val27-after.json --port $P --timeout 1800 > logs/val27-after.log 2>&1
note "CONTRÔLES APRÈS rc=$? $(tail -1 logs/val27-after.log)"
kill $(ps -C llama-server -o pid=,args= | awk -v p="--port $P" 'index($0,p) {print $1}')
note "FIN"
