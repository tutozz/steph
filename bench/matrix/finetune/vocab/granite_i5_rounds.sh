#!/bin/bash
# Vitesse i5 (protocole A8 : 4 threads, CPU, ctx 4096, parallel 1), rondes alternées complet/réduit.
# Avant chaque passage : attente tant qu'un autre llama-server tourne.
set -u
cd /root/stephbench-ft
SERVER=/root/stephbench-g2/bin/llama-b11205/llama-server
CASES=/root/stephbench-ft/cases_ft36.json
mkdir -p results
run() {
  local n=$1 k=$2
  while pgrep -x llama-server >/dev/null; do echo "attente : llama-server étranger $(date -Is)"; sleep 30; done
  label="i5-vocab-granite-$n-Q4_K_M-p$(printf %02d $k)"
  echo "=== DEBUT $label $(date -Is) ==="
  python3 bench_run.py --server "$SERVER" --model "models/vocab-granite-$n-Q4_K_M.gguf" --label "$label" \
    --out "results/${label}.json" --cases "$CASES" --threads 4 --ngl 0 --ctx 4096 --parallel 1 --port 8899
  echo "=== FIN $label $(date -Is) ==="
}
k=0
for n in full c32768 full c65536 full b32768 b32768 full c65536 full c32768 full; do
  k=$((k+1)); run $n $k
done
echo "=== TOUT FINI ==="
