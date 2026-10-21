#!/bin/bash
# Serveurs llama.cpp (complet + 3 réduits) sur coeurs 0-15, vérification de tokenisation, arrêt par PID.
cd /root/steph-ft/vocab
L=/root/steph-ft/llama/llama-b11205
start() { systemd-run --scope --quiet -p AllowedCPUs=$3 -p MemoryMax=8G nice -n 19 env LD_LIBRARY_PATH=$L:/root/steph-ft/vendor/lib \
  $L/llama-server -m gguf/$1-Q4_K_M.gguf --host 127.0.0.1 --port $2 -t 4 -c 4096 --no-webui --jinja > logs/srv-$1.log 2>&1 & echo $! > logs/srv-$1.pid; }
start full 8921 0-3; start c32768 8922 4-7; start c65536 8923 8-11; start b32768 8924 12-15
for p in 8921 8922 8923 8924; do for i in $(seq 60); do curl -sf http://127.0.0.1:$p/health >/dev/null && break; sleep 1; done; done
i=8922
for n in c32768 c65536 b32768; do
  nice -n 19 ../venv/bin/python granite_verify_llamacpp.py 8921 $i gguf/$n-f16.gguf.map.json hftok tok/evalset.jsonl tok/cases_ft.jsonl > tok/lcpp-verify-$n.json 2> logs/lcpp-verify-$n.err &
  i=$((i+1))
done
wait $(jobs -p | tail -3) 2>/dev/null
for n in full c32768 c65536 b32768; do kill $(cat logs/srv-$n.pid); done
echo LCPP-VERIFY-DONE
