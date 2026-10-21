#!/bin/bash
# G3 éval : formulation à l oral (judge_style_v3.py, Qwen3.5 27B Q4_K_M 84b5f7f1, verdict global) sur la 3080 en déport partiel,
# split test, graine 7, 240 paires différentes tirées par hachage (style_sample.py, même tirage que R2). Après les couloirs de génération.
#   style.sh <x> <y> [<x> <y> ...]
set -u
W=/root/steph-ft/g3/eval; T=$W/repo/bench/matrix/v3/tools; P=8998; N=${N:-240}; NGL=${NGL:-32}
M=/dev/shm/g3-style-Qwen3.5-27B-Q4_K_M.gguf; SRV=/root/steph-ft/llama.cpp/build/bin/llama-server
note() { echo "$(date +%T) $*" >> $W/style.done; }
cd $W; mkdir -p style
note "ATTENTE couloirs finis et 27B copié"
until [ "$(grep -c "LANE .* FIN" logs/done.log)" -ge 4 ] && [ -f $M.ok ]; do sleep 60; done
until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge 9500 ]; do sleep 60; done
nice -n 5 $SRV -m $M --host 127.0.0.1 --port $P -c 8192 -ngl $NGL -t 16 --parallel 2 --jinja --no-webui -ub 512 > logs/srv27.log 2>&1 < /dev/null &
echo $! > style-srv.pid
for i in $(seq 300); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:$P/health > /dev/null || { note "27B KO"; exit 1; }
note "27B PRÊT ngl $NGL $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"
while [ $# -ge 2 ]; do
  x=$1; y=$2; shift 2
  python3 $T/style_sample.py runs/$x-test-b7.json runs/$y-test-b7.json $N style/$x-vs-$y-x.json style/$x-vs-$y-y.json > style/sample-$x-vs-$y.json
  note "PAIRES $x contre $y $(cat style/sample-$x-vs-$y.json)"
  python3 $T/judge_style_v3.py run $W/harness/test.generic.json style/style-$x-vs-$y.json \
    --a style/$x-vs-$y-x.json --b style/$x-vs-$y-y.json --ports $P,$P > logs/style-$x-vs-$y.log 2>&1
  note "STYLE $x contre $y rc=$?"
done
kill $(cat style-srv.pid); rm -f style-srv.pid
note "FIN"
