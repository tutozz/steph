#!/bin/bash
# T4 reprise : garde « machine calme » avant chaque banc, charge étrangère journalisée.
set -u
T=/root/steph-ft/loop/t4
NAT=/root/steph-ft/llama/llama-b11205
HSW=$T/llama-hsw
VL=/root/steph-ft/vendor/lib
cd $T
scope() { systemd-run --scope --quiet -p AllowedCPUs=$1 -p MemoryMax=64G nice -n 19 "${@:2}"; }
wait_quiet() { # attend que les 48 threads soient calmes (< 2 cœurs occupés), 3 h max
  local i=0
  while [ $(python3 busy.py 0 47 3 | awk '{print ($1>2.0)}') = 1 ]; do
    [ $i = 0 ] && echo "$(date +%T) attente machine calme" >> logs/quiet.log
    i=$((i+1)); [ $i -gt 180 ] && { echo "$(date +%T) délai dépassé, on mesure quand même" >> logs/quiet.log; return; }
    sleep 57
  done
}
run_bench() { # build cpus threads cases maxc label model
  local bin=$1 cpus=$2 th=$3 cases=$4 maxc=$5 label=$6 m=$7
  [ -f res/$label.json ] && return
  wait_quiet
  python3 busy.py 4 47 1 > logs/$label.foreign-before
  scope $cpus env LD_LIBRARY_PATH=$bin:$VL python3 bench_run.py --server $bin/llama-server --model $m \
    --label $label --out res/$label.json --cases $cases --maxc $maxc --threads $th --ctx 4096 --ubatch 512 --port 8942 > logs/$label.log 2>&1
  python3 busy.py 4 47 1 > logs/$label.foreign-after
}
for pass in 1 2; do
  for m in $(ls q/*.gguf | shuf --random-source=<(yes $pass)); do
    n=$(basename $m .gguf)
    run_bench $HSW 0-3 4 cases.json 1500 hsw4-ft36-$n-p$pass $m
    run_bench $HSW 0-3 4 cases_compact_granite200_train.json 0 hsw4-b3-$n-p$pass $m
    [ $pass = 1 ] && run_bench $NAT 0-3 4 cases.json 1500 nat4-ft36-$n-p1 $m
    [ $pass = 1 ] && run_bench $NAT 0-31 32 cases.json 1500 nat32-ft36-$n-p1 $m
  done
done
for m in q/*.gguf; do
  n=$(basename $m .gguf)
  [ -s res/lb-hsw4-$n.json ] && continue
  wait_quiet
  scope 0-3 env LD_LIBRARY_PATH=$HSW:$VL $HSW/llama-bench -m $m -t 4 -p 128,512 -n 64 -ub 512 -r 3 -o json > res/lb-hsw4-$n.json 2> logs/lb-hsw4-$n.log
done
echo ALLDONE
