#!/bin/bash
# G6 : filtre de vitesse des MoE bruts sur l'i5-7200U, même méthode que G2 (g2_run.sh) :
# 36 cas (granite_ram.py) puis 151 résumés dev v3 au format generic (bench_run.py), réglages de production
# generic (-c 32768 --parallel 2 -b 512 -ub 512 -t 4) ; --cache-ram 0 sur les modèles à état récurrent
# (Mamba, convolutions courtes, attention linéaire), sinon défaut de production. Questions P20 (froid,
# préchauffé) seulement si le p90 des résumés tient sous 8 s. Une mesure à la fois ; GGUF téléchargé,
# sha256 vérifié, supprimé à la fin.
# usage : g6_i5.sh <label> <dépôt HF> <fichier> <sha256> <rec|std>
set -u
lab=$1; repo=$2; file=$3; sha=$4; kind=$5
cd /root/g6; mkdir -p res models
SRV=/root/stephbench-g2/bin/llama-b11205/llama-server; R=/root/g2/repo; M=/root/g6/models/$file
idle() { while [ "$(LC_ALL=C awk '{print ($1<0.3)}' /proc/loadavg)" != 1 ] || pgrep -x llama-server >/dev/null || pgrep -x piper >/dev/null; do sleep 10; done; }
log() { echo "$(date +%T) load $(cut -d' ' -f1 /proc/loadavg) $*" >> run.log; }
cram=8192; cx=""; [ $kind = rec ] && cram=0 && cx="--cache-ram 0"
[ -f $M ] || curl -sL --retry 5 -o $M "https://huggingface.co/$repo/resolve/main/$file"
got=$(sha256sum $M | cut -d' ' -f1); [ "$got" = "$sha" ] || { log "$lab SHA KO $got"; exit 1; }
log "$lab sha OK $(stat -c %s $M)"
if [ ! -f res/$lab-36.json ]; then
  idle; log "$lab 36"
  python3 $R/bench/perf/granite_ram.py --server $SRV --model $M --label $lab-36 --out res/$lab-36.json \
    --cases /root/stephbench-ft/cases_ft36.json --maxc 1500 --ctx 32768 --ubatch 512 --batch 512 --parallel 2 --threads 4 \
    --timeout 600 --extra="$cx" >> run.log 2>&1
fi
if [ ! -f res/$lab-sum-dev.json ]; then
  idle; log "$lab sum dev"
  python3 $R/bench/matrix/bench_run.py --server $SRV --model $M --label $lab-sum-dev --out res/$lab-sum-dev.json \
    --cases /root/g2/dev_sum_rm.json --maxc 0 --ctx 32768 --ubatch 512 --parallel 2 --threads 4 --cache-ram $cram \
    --abort-ttft 600 --timeout 900 >> run.log 2>&1
fi
p90=$(python3 -c "import json; print(json.load(open('res/$lab-sum-dev.json')).get('ttft_p90') or 999)")
log "$lab résumés p90 $p90"
if python3 -c "import sys; sys.exit(0 if $p90 <= 8 else 1)"; then
  for regime in cold warm; do
    [ -f res/$lab-qa-$regime.json ] && continue
    idle; log "$lab qa $regime"
    $SRV -m $M --host 127.0.0.1 --port 8972 -c 32768 -ngl 0 --parallel 2 --no-webui --jinja -b 512 -ub 512 \
      --reasoning-budget 0 -t 4 $cx --slot-save-path /root/g6/slots > res/$lab-qa-$regime.server.log 2>&1 &
    spid=$!; t0=$(date +%s.%N)
    until curl -sf http://127.0.0.1:8972/health >/dev/null; do kill -0 $spid 2>/dev/null || exit 1; sleep 0.3; done
    echo "load_s $(echo "$(date +%s.%N) - $t0" | bc)" > res/$lab-qa-$regime.ram
    ( peak=0; while kill -0 $spid 2>/dev/null; do r=$(ps -o rss= -p $spid | tr -d ' '); [ -n "$r" ] && [ "$r" -gt "$peak" ] && peak=$r && echo "peak_mb $((peak/1024))" > res/$lab-qa-$regime.peak; sleep 0.5; done ) &
    mkdir -p /root/g6/slots
    PYTHONUTF8=1 python3 $R/bench/matrix/p20_qa_latency.py --cases $R/bench/matrix/v3/cases/dev/history-qa.jsonl \
      --port 8972 --regime $regime --profile generic --out res/$lab-qa-$regime.json >> run.log 2>&1
    kill $spid; wait $spid 2>/dev/null
  done
fi
rm -f $M
log "DONE $lab"
