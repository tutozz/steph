#!/bin/bash
# G3b éval : banc v3 test aligné L5 (générique 8d90a662, affiné 705fdcb9), 3080 CUDA llama.cpp 9588757 (celui de G3),
# l'A1000 étant devenue injoignable à 17:18. lane-3080.sh <port> ; file jobs.q partagée, ligne : <modèle> <test|test.generic> <graine>.
set -u
W=/root/steph-ft/g3b; Q=$W/jobs.q; port=$1
while :; do
  job=$(flock $Q.lock sh -c "head -1 $Q; sed -i 1d $Q")
  [ -z "$job" ] && break
  set -- $job; m=$1; h=$2; sd=$3
  OUT=$W/runs/$m-test-b$sd.json
  [ -f $OUT ] && continue
  until [ -e $W/gguf/$m.ok ]; do sleep 60; done
  while [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)" -lt 4000 ]; do sleep 60; done
  nice -n 5 python3 $W/repo/bench/matrix/bench_run.py --server /root/steph-ft/llama.cpp/build/bin/llama-server --model $W/gguf/$m.gguf \
    --label g3b-$m-v3test-l5-cuda-b$sd --cases $W/harness/$h.json --maxc 0 --port $port --ngl 99 --abort-ttft 120 \
    --payload "{\"seed\": $sd}" --out $OUT >> $W/logs/lane-$port.log 2>&1
  echo "$(date +%T) $m b$sd rc=$?" >> $W/logs/done.log
done
echo "$(date +%T) LANE $port FIN" >> $W/logs/done.log
