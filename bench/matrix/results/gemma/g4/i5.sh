#!/bin/bash
# G4 : variantes Gemma 4 E2B sur l'i5-7200U, production generic (réglages de G2), une mesure à la fois.
#   50 résumés dev v3 reaches_model (un sur trois du sous-ensemble G2 de 151), bench_run.py, 1er jeton, RAM pic, chargement.
#   i5.sh <variante>... ; GGUF /root/g4/gguf/<variante>.gguf, visible quand .ok existe.
cd /root/g4; mkdir -p res
SRV=/root/stephbench-g2/bin/llama-b11205/llama-server; R=/root/g2/repo
[ -f sum50.json ] || python3 -c "
import json;s=json.load(open('/root/g2/dev_sum_rm.json'));json.dump(s[0:len(s):3],open('sum50.json','w'),ensure_ascii=False);print(len(s[0:len(s):3]))"
idle() { while [ "$(LC_ALL=C awk '{print ($1<0.3)}' /proc/loadavg)" != 1 ] || pgrep -x llama-server >/dev/null || pgrep -x piper >/dev/null; do sleep 20; done; }
log() { echo "$(date +%T) load $(cut -d' ' -f1 /proc/loadavg) $*" >> run.log; }
for m in "$@"; do
  [ -f res/$m.json ] && continue
  until [ -f gguf/$m.ok ]; do sleep 60; done
  idle; log "g4 $m"
  python3 $R/bench/matrix/bench_run.py --server $SRV --model /root/g4/gguf/$m.gguf --label g4-$m-i5 --out res/$m.json \
    --cases sum50.json --maxc 0 --ctx 32768 --ubatch 512 --parallel 2 --threads 4 --cache-ram 8192 \
    --abort-ttft 600 --timeout 900 >> run.log 2>&1
  log "g4 $m rc=$?"
done
log "ALLDONE"
