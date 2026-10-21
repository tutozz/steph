#!/bin/bash
# G4b : banc v3 test aligné L5 (générique 8d90a662), 3080 CUDA, llama.cpp 9588757 (celui de G3b), bench_run.py de G3b.
#   lane.sh <port> ; file jobs.q partagée, ligne : <modèle> <graine> ; GGUF /dev/shm/g4b/<fichier> via gguf/<modèle>.gguf.
set -u
W=/root/steph-ft/g4b; Q=$W/jobs.q; port=$1
while :; do
  job=$(flock $Q.lock sh -c "head -1 $Q; sed -i 1d $Q")
  [ -z "$job" ] && break
  set -- $job; m=$1; sd=$2
  OUT=$W/runs/$m-test-b$sd.json
  [ -f $OUT ] && continue
  until [ -e $W/gguf/$m.ok ]; do sleep 30; done
  while [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)" -lt 4000 ]; do sleep 60; done
  nice -n 5 python3 /root/steph-ft/g3b/repo/bench/matrix/bench_run.py --server /root/steph-ft/llama.cpp/build/bin/llama-server \
    --model $W/gguf/$m.gguf --label g4b-$m-v3test-l5-cuda-b$sd --cases $W/harness/test.generic.json --maxc 0 --port $port --ngl 99 \
    --abort-ttft 120 --payload "{\"seed\": $sd}" --out $OUT >> $W/logs/lane-$port.log 2>&1
  echo "$(date +%T) $m b$sd rc=$?" >> $W/logs/done.log
done
echo "$(date +%T) LANE $port FIN" >> $W/logs/done.log
