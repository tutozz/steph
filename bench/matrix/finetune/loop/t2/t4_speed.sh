#!/bin/bash
# T2 sur le proxy T4 (AVX2 seule, 4 cœurs, bench_run.py B3 36 cas, garde machine calme), 2 passes ordre aléatoire, puis llama-bench
set -u
T4=/root/steph-ft/loop/t4; T=/root/steph-ft/loop/t2; HSW=$T4/llama-hsw; VL=/root/steph-ft/vendor/lib
cd $T; mkdir -p t4res t4logs
scope() { systemd-run --scope --quiet -p AllowedCPUs=$1 -p MemoryMax=64G nice -n 19 "${@:2}"; }
wait_quiet() {
  local i=0
  while [ $(python3 $T4/busy.py 0 47 3 | awk '{print ($1>2.0)}') = 1 ]; do
    [ $i = 0 ] && echo "$(date +%T) attente machine calme" >> t4logs/quiet.log
    i=$((i+1)); [ $i -gt 180 ] && { echo "$(date +%T) délai dépassé, on mesure quand même" >> t4logs/quiet.log; return; }
    sleep 57
  done
}
for pass in 1 2; do
  for m in $(ls gguf/k3-a-dpo-Q4_K_M.gguf gguf/t2-cut*-Q4_K_M.gguf | shuf --random-source=<(yes $pass)); do
    n=$(basename $m .gguf); label=hsw4-b3-$n-p$pass
    [ -f t4res/$label.json ] && continue
    wait_quiet
    python3 $T4/busy.py 4 47 1 > t4logs/$label.foreign-before
    scope 0-3 env LD_LIBRARY_PATH=$HSW:$VL python3 $T4/bench_run.py --server $HSW/llama-server --model $m --label $label \
      --out t4res/$label.json --cases $T4/cases_compact_granite200_train.json --maxc 0 --threads 4 --ctx 4096 --ubatch 512 --port 8943 > t4logs/$label.log 2>&1
    python3 $T4/busy.py 4 47 1 > t4logs/$label.foreign-after
  done
done
for m in gguf/k3-a-dpo-Q4_K_M.gguf gguf/t2-cut*-Q4_K_M.gguf; do
  n=$(basename $m .gguf); [ -s t4res/lb-hsw4-$n.json ] && continue
  wait_quiet
  scope 0-3 env LD_LIBRARY_PATH=$HSW:$VL $HSW/llama-bench -m $m -t 4 -p 128,512 -n 64 -ub 512 -r 3 -o json > t4res/lb-hsw4-$n.json 2> t4logs/lb-hsw4-$n.log
done
echo ALLDONE > t4res/DONE
