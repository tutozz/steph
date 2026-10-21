#!/bin/bash
# T4 : banc proxy de vitesse sur xeon. Séquentiel, un seul serveur à la fois.
set -u
T=/root/steph-ft/loop/t4
NAT=/root/steph-ft/llama/llama-b11205
HSW=$T/llama-hsw
export LD_LIBRARY_PATH_BASE=/root/steph-ft/vendor/lib
cd $T
scope() { systemd-run --scope --quiet -p AllowedCPUs=$1 -p MemoryMax=64G nice -n 19 "${@:2}"; }
# 1) quantification
for s in src/*.gguf; do
  b=$(basename $s .gguf); tag=$(echo $b | sed -E 's/[-_.](bf16|BF16|f16|F16)$//' | tr 'A-Z' 'a-z')
  for q in Q8_0 Q4_K_M Q4_0; do
    [ -f q/$tag-$q.gguf ] || scope 0-31 env LD_LIBRARY_PATH=$NAT:$LD_LIBRARY_PATH_BASE $NAT/llama-quantize $s q/$tag-$q.gguf $q 32 > logs/quant-$tag-$q.log 2>&1
  done
done
sha256sum q/*.gguf > res/sha256.txt
# 2) jetons par tokeniseur (une quantification suffit)
for m in q/*-Q8_0.gguf; do
  tag=$(basename $m -Q8_0.gguf)
  [ -f res/tok-$tag.json ] || scope 0-3 env LD_LIBRARY_PATH=$HSW:$LD_LIBRARY_PATH_BASE python3 tokcount.py $HSW/llama-server $m res/tok-$tag.json
done
# 3) bancs : pass=$1 (ordre des modèles aléatoire pour ne pas corréler dérive thermique et modèle)
run_bench() { # build cpus threads cases maxc label model
  local bin=$1 cpus=$2 th=$3 cases=$4 maxc=$5 label=$6 m=$7
  [ -f res/$label.json ] && return
  scope $cpus env LD_LIBRARY_PATH=$bin:$LD_LIBRARY_PATH_BASE python3 bench_run.py --server $bin/llama-server --model $m \
    --label $label --out res/$label.json --cases $cases --maxc $maxc --threads $th --ctx 4096 --ubatch 512 --port 8942 > logs/$label.log 2>&1
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
# 4) llama-bench préremplissage/génération
for m in q/*.gguf; do
  n=$(basename $m .gguf)
  [ -f res/lb-hsw4-$n.json ] || scope 0-3 env LD_LIBRARY_PATH=$HSW:$LD_LIBRARY_PATH_BASE $HSW/llama-bench -m $m -t 4 -p 128,512 -n 64 -ub 512 -r 3 -o json > res/lb-hsw4-$n.json 2> logs/lb-hsw4-$n.log
done
echo ALLDONE
