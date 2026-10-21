#!/bin/bash
# G2 : Gemma 4 E2B brut (QAT q4_0, sha256 fa401b55) sur l'i5-7200U, profil generic de production.
# Production generic (llm.py, cpu.toml, config.py) : -c 32768 --parallel 2 -b 512 -ub 512 -ngl 0, pas de --cache-ram
# (défaut llama-server 8192 Mo) ; -t 4 comme toutes les mesures i5 précédentes. Une mesure à la fois.
cd /root/g2; mkdir -p res
SRV=/root/stephbench-g2/bin/llama-b11205/llama-server; M=/root/g2/gemma-4-E2B_q4_0-it.gguf; R=/root/g2/repo
idle() { while [ "$(LC_ALL=C awk '{print ($1<0.3)}' /proc/loadavg)" != 1 ] || pgrep -x llama-server >/dev/null || pgrep -x piper >/dev/null; do sleep 10; done; }
log() { echo "$(date +%T) load $(cut -d' ' -f1 /proc/loadavg) $*" >> run.log; }
step="${1:-all}"
if [ "$step" = all ] || [ "$step" = 36 ]; then
  idle; log "g2 36"
  python3 $R/bench/perf/granite_ram.py --server $SRV --model $M --label gemma-36 --out res/gemma-36.json \
    --cases /root/stephbench-ft/cases_ft36.json --maxc 1500 --ctx 32768 --ubatch 512 --batch 512 --parallel 2 --threads 4 \
    --timeout 600 >> run.log 2>&1
fi
if [ "$step" = all ] || [ "$step" = var ]; then
  for spec in "cram0-c32768|32768|4|--cache-ram 0" "cram0-c8192|8192|4|--cache-ram 0" "tdefault|32768|0|"; do
    IFS='|' read lab ctx th ex <<< "$spec"; idle; log "g2 36 $lab"
    targs="--threads $th"; [ "$th" = 0 ] && targs="--threads -1"
    python3 $R/bench/perf/granite_ram.py --server $SRV --model $M --label gemma-36-$lab --out res/gemma-36-$lab.json \
      --cases /root/stephbench-ft/cases_ft36.json --maxc 1500 --ctx $ctx --ubatch 512 --batch 512 --parallel 2 $targs \
      --timeout 600 --extra "$ex" >> run.log 2>&1
  done
fi
if [ "$step" = all ] || [ "$step" = sum ]; then
  python3 -c "
import json;r=json.load(open('dev.generic.json'))
s=[x for x in r if x['reaches_model'] and x['kind']=='summary'];json.dump(s[0:len(s):3],open('dev_sum_rm.json','w'),ensure_ascii=False)"
  idle; log "g2 sum dev"
  python3 $R/bench/matrix/bench_run.py --server $SRV --model $M --label gemma-sum-dev --out res/gemma-sum-dev.json \
    --cases dev_sum_rm.json --maxc 0 --ctx 32768 --ubatch 512 --parallel 2 --threads 4 --cache-ram 8192 \
    --abort-ttft 600 --timeout 900 >> run.log 2>&1
fi
for regime in cold warm; do
  if [ "$step" = all ] || [ "$step" = qa ] || [ "$step" = "qa-$regime" ]; then
    idle; log "g2 qa $regime"
    $SRV -m $M --host 127.0.0.1 --port 8972 -c 32768 -ngl 0 --parallel 2 --no-webui --jinja -b 512 -ub 512 \
      --reasoning-budget 0 -t 4 --slot-save-path /root/g2/slots > res/qa-$regime.server.log 2>&1 &
    spid=$!; t0=$(date +%s.%N)
    until curl -sf http://127.0.0.1:8972/health >/dev/null; do kill -0 $spid 2>/dev/null || exit 1; sleep 0.3; done
    echo "load_s $(echo "$(date +%s.%N) - $t0" | bc)" > res/qa-$regime.ram
    ( peak=0; while kill -0 $spid 2>/dev/null; do r=$(ps -o rss= -p $spid | tr -d ' '); [ -n "$r" ] && [ "$r" -gt "$peak" ] && peak=$r && echo "peak_mb $((peak/1024))" > res/qa-$regime.peak; sleep 0.5; done ) &
    mkdir -p /root/g2/slots
    PYTHONUTF8=1 python3 $R/bench/matrix/p20_qa_latency.py --cases $R/bench/matrix/v3/cases/dev/history-qa.jsonl \
      --port 8972 --regime $regime --profile generic --out res/qa-$regime.json >> run.log 2>&1
    kill $spid; wait $spid 2>/dev/null
  fi
done
log "ALLDONE $step"
