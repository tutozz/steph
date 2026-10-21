#!/bin/bash
# G3 éval : banc v3 test (HEAD après X5, harnais identique à a52223c), 3080 CUDA, une file de travaux partagée.
#   lane.sh <port> <file de travaux> ; ligne : <étiquette> <harnais test|test.generic> <graine>
set -u
W=/root/steph-ft/g3/eval; port=$1; Q=$2
while :; do
  job=$(flock $Q.lock sh -c "head -1 $Q; sed -i 1d $Q")
  [ -z "$job" ] && break
  set -- $job; m=$1; h=$2; sd=$3
  OUT=$W/runs/$m-test-b$sd.json
  [ -f $OUT ] && continue
  until [ -f $W/gguf/$m.ok ]; do sleep 30; done
  nice -n 5 python3 $W/repo/bench/matrix/bench_run.py --server /root/steph-ft/llama.cpp/build/bin/llama-server \
    --model $W/gguf/$m.gguf --label g3-$m-v3test-cuda-b$sd --cases $W/harness/$h.json \
    --maxc 0 --port $port --ngl 99 --abort-ttft 120 --payload "{\"seed\": $sd}" --out $OUT >> $W/logs/lane-$port.log 2>&1
  echo "$(date +%T) $m b$sd rc=$?" >> $W/logs/done.log
done
echo "$(date +%T) LANE $port FIN" >> $W/logs/done.log
