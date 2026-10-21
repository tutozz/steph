#!/bin/bash
# Banc steph (cases_ft, prompt système court, rp 1.1, graines 42 7 123) sur xeon CPU :
# une voie de 8 coeurs par modèle (0-31), graines en séquence dans chaque voie.
cd /root/steph-ft/vocab/bench
L=/root/steph-ft/llama/llama-b11205
lane() {
  local n=$1 lo=$2 port=$3
  for sd in 42 7 123; do
    systemd-run --scope --quiet -p AllowedCPUs=$lo-$((lo+7)) -p MemoryMax=16G nice -n 19 env LD_LIBRARY_PATH=$L:/root/steph-ft/vendor/lib \
      python3 bench_run.py --server $L/llama-server --model ../gguf/$n-Q4_K_M.gguf --label vocab-granite-$n-Q4_K_M-b$sd \
      --threads 8 --ngl 0 --ctx 4096 --parallel 1 --port $port --cases cases_ft.json \
      --payload "{\"repeat_penalty\": 1.1, \"seed\": $sd}" --out ../results/granite-$n-Q4_K_M-b$sd.json >> ../logs/bench-$n.log 2>&1
  done
  echo "LANE-DONE $n" >> ../logs/bench.done
}
lane full 0 8931 & lane c32768 8 8932 & lane c65536 16 8933 & lane b32768 24 8934 &
wait
echo BENCH-ALL-DONE >> ../logs/bench.done
