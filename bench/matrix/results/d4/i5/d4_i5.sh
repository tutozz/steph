#!/bin/bash
# D4 : latence des questions sur l'i5, Gemma 4 E2B brut, mode actuel contre mode outils. Une passe à la fois.
cd /root/d4
SRV=/root/stephbench-g2/bin/llama-b11205/llama-server; M=/root/d4/gemma-4-E2B_q4_0-it.gguf
IDS=$(head -1 ids.txt)
idle() { while [ "$(LC_ALL=C awk '{print ($1<0.3)}' /proc/loadavg)" != 1 ] || pgrep -x llama-server >/dev/null || pgrep -x piper >/dev/null; do sleep 10; done; }
log() { echo "$(date +%T) load $(cut -d' ' -f1 /proc/loadavg) $*" >> run.log; }
for spec in "cur:cold:" "tools:cold:--qa-tools" "cur:warm:" "tools:warm:--qa-tools"; do
  IFS=: read mode regime flag <<< "$spec"
  [ -f runs/$mode-$regime.ok ] && continue
  idle; log "start $mode $regime"
  $SRV -m $M --host 127.0.0.1 --port 8974 -c 32768 -ngl 0 --parallel 2 --no-webui --jinja -b 512 -ub 512 \
    --reasoning-budget 0 -t 4 --slot-save-path /root/d4/slots > runs/$mode-$regime.server.log 2>&1 &
  spid=$!
  until curl -sf http://127.0.0.1:8974/health >/dev/null; do kill -0 $spid 2>/dev/null || exit 1; sleep 0.3; done
  python3 p20_qa_latency.py --cases history-qa.jsonl --port 8974 --regime $regime --profile generic --seed 7 \
    --ids "$IDS" --out runs/$mode-$regime.json $flag > runs/$mode-$regime.log 2>&1 && touch runs/$mode-$regime.ok
  kill $spid; wait $spid 2>/dev/null
  log "end $mode $regime"
done
