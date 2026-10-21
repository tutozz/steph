#!/bin/bash
# G4b : G3b Q4_0 contre G3b off-ple3 sur l'i5-7200U, production generic (réglages de G2 et G4), une mesure à la fois.
#   51 résumés dev v3 reaches_model (sum50.json de G4), bench_run.py, 1er jeton, RAM pic.
#   i5.sh <étiquette>:<GGUF sans .gguf> ... ; ex. i5.sh a-q4_0:q4_0 a-off-ple3:off-ple3 b-off-ple3:off-ple3 b-q4_0:q4_0
cd /root/g4b; mkdir -p res
SRV=/root/stephbench-g2/bin/llama-b11205/llama-server; R=/root/g2/repo; S=/root/g4/sum50.json
idle() { while [ "$(LC_ALL=C awk '{print ($1<0.3)}' /proc/loadavg)" != 1 ] || pgrep -x llama-server >/dev/null || pgrep -x piper >/dev/null; do sleep 20; done; }
log() { echo "$(date +%T) load $(cut -d' ' -f1 /proc/loadavg) $*" >> run.log; }
for a in "$@"; do
  l=${a%%:*}; m=${a##*:}
  [ -f res/$l.json ] && continue
  idle; log "g4b $l"
  python3 $R/bench/matrix/bench_run.py --server $SRV --model /root/g4b/gguf/$m.gguf --label g4b-$l-i5 --out res/$l.json \
    --cases $S --maxc 0 --ctx 32768 --ubatch 512 --parallel 2 --threads 4 --cache-ram 8192 \
    --abort-ttft 600 --timeout 900 >> run.log 2>&1
  log "g4b $l rc=$?"
done
log "ALLDONE"
