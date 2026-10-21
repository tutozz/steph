#!/bin/bash
# G3b éval : banc v3 test aligné L5 (générique 8d90a662, affiné 705fdcb9), A1000 Vulkan llama b11205 (95887577), un seul couloir.
#   lane-a1000.sh ; file jobs.q, ligne : <modèle> <test|test.generic> <graine> ; GGUF gguf/<modèle>.gguf, attendu tant qu'absent.
set -u
W=/root/steph-ft/g3b; Q=$W/jobs.q
while :; do
  job=$(flock $Q.lock sh -c "head -1 $Q; sed -i 1d $Q")
  [ -z "$job" ] && break
  set -- $job; m=$1; h=$2; sd=$3
  OUT=$W/runs/$m-test-b$sd.json
  [ -f $OUT ] && continue
  until [ -e $W/gguf/$m.ok ]; do sleep 60; done
  python3 $W/repo/bench/matrix/bench_run.py --server /root/steph-ft/llama/vulkan/llama-server --model $W/gguf/$m.gguf \
    --label g3b-$m-v3test-l5-a1000-b$sd --cases $W/harness/$h.json --maxc 0 --port 8983 --ngl 99 --abort-ttft 120 \
    --payload "{\"seed\": $sd}" --out $OUT >> $W/logs/lane.log 2>&1
  echo "$(date +%T) $m b$sd rc=$?" >> $W/logs/done.log
done
echo "$(date +%T) FIN" >> $W/logs/done.log
