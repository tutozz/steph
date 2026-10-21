#!/bin/bash
# CONTROL : formulation à l oral, off-ple3 (G4) contre Q4_0 officiel, graine 7, harnais générique pré-L5 (md5 1ea3b078), 240 paires par hachage.
# Config validée en G3b sur ce CPU : un slot, --cache-ram 0, cœurs 0-31, 64 Go, nice 19. Contrôles plantés X5 avant ET après.
# Attend la fin du 27B de G3b : un seul 27B à la fois sur xeon.
set -u
C=/root/steph-ft/control; R=/root/steph-ft/g3b/repo/bench/matrix; T=$R/v3/tools; P=8993
M=/root/steph-ft/x4a/models/Qwen3.5-27B-Q4_K_M.gguf; SRV=/root/steph-ft/llama/llama-b11205/llama-server
note() { echo "$(date +%T) $*" >> $C/style.done; }
cd $C; mkdir -p style logs
note "ATTENTE fin du 27B de G3b"
until ! ps -C llama-server -o args= | grep -q Qwen3.5-27B; do sleep 60; done
until [ "$(awk "/MemAvailable/ {print int(\$2/1048576)}" /proc/meminfo)" -ge 40 ]; do sleep 60; done
export LD_LIBRARY_PATH=/root/steph-ft/llama/llama-b11205:/root/steph-ft/vendor/lib
systemd-run --scope -q -p AllowedCPUs=0-31 -p MemoryMax=64G nice -n 19 $SRV -m $M --host 127.0.0.1 --port $P -c 8192 -t 32 \
  --parallel 1 --cache-ram 0 --jinja --no-webui -ub 512 > logs/srv27.log 2>&1 < /dev/null &
for i in $(seq 300); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:$P/health > /dev/null || { note "27B KO"; exit 1; }
note "27B PRÊT"
python3 $T/judge_style_v3.py controls $R/v3/x5/controls.jsonl style/controls-pre.json --ports $P,$P > logs/controls-pre.log 2>&1; note "CONTRÔLES avant rc=$?"
python3 $R/finetune/r2/style_sample.py runs/g4-off-ple3-test-b7.json runs/gemma-raw-test-b7.json 240 style/x.json style/y.json > style/sample.json
note "PAIRES off-ple3 contre officiel $(cat style/sample.json)"
python3 $T/judge_style_v3.py run runs/test.generic.json style/style-off-ple3-vs-official.json --a style/x.json --b style/y.json --ports $P,$P > logs/style.log 2>&1; note "STYLE rc=$?"
python3 $T/judge_style_v3.py controls $R/v3/x5/controls.jsonl style/controls-post.json --ports $P,$P > logs/controls-post.log 2>&1; note "CONTRÔLES après rc=$?"
kill $(ps -C llama-server -o pid=,args= | awk -v p="--port $P" "index(\$0,p) {print \$1}")
note "FIN"
