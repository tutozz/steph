#!/bin/bash
# G2 : où vont les 4,5 Go de Gemma sur l'i5 ; mêmes 36 cas, réglages de production generic plus un levier à la fois.
cd /root/g2
SRV=/root/stephbench-g2/bin/llama-b11205/llama-server; M=/root/g2/gemma-4-E2B_q4_0-it.gguf; R=/root/g2/repo
idle() { while [ "$(LC_ALL=C awk '{print ($1<0.3)}' /proc/loadavg)" != 1 ] || pgrep -x llama-server >/dev/null || pgrep -x piper >/dev/null; do sleep 10; done; }
log() { echo "$(date +%T) load $(cut -d' ' -f1 /proc/loadavg) $*" >> run.log; }
for spec in "lmnone:-lm none"; do
  IFS=: read lab ex <<< "$spec"; idle; log "g2 36 $lab"
  python3 $R/bench/perf/granite_ram.py --server $SRV --model $M --label gemma-36-$lab --out res/gemma-36-$lab.json \
    --cases /root/stephbench-ft/cases_ft36.json --maxc 1500 --ctx 32768 --ubatch 512 --batch 512 --parallel 2 --threads 4 \
    --timeout 600 --extra="$ex" >> run.log 2>&1
done
log "ALLDONE ram"
