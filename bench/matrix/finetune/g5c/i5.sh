#!/bin/bash
# G5c : i5-7200U, réglages de production (cpu.toml : -c 8192 --parallel 2 -t 4 --cache-ram 0 -ub 512 -b 512), b11205,
# protocole de R2 (r2/i5_run.sh) : une mesure à la fois, machine au repos avant chaque passe, la référence et la variante
# alternés, deux passes chacun ; 36 cas (granite_ram.py : 1er jeton, RAM pic), puis 90 questions dev v3 à froid.
#   i5.sh <référence> <variante> ; dans /root/g5c, GGUF dans gguf/<nom>-Q4_K_M.gguf (a-sft et v10 : liens vers /root/g5/gguf)
set -u
REF=$1; X=$2
cd /root/g5c; mkdir -p res
SRV=/root/stephbench-g2/bin/llama-b11205/llama-server; G=/root/g5c/gguf
idle() { while [ "$(LC_ALL=C awk '{print ($1<0.3)}' /proc/loadavg)" != 1 ] || pgrep -x llama-server > /dev/null; do sleep 10; done; }
for spec in $REF:1 $X:1 $REF:2 $X:2; do
  m=${spec%%:*}; p=${spec##*:}; idle
  echo "$(date +%T) load $(cut -d' ' -f1 /proc/loadavg) $m 36 p$p" >> run.log
  [ -f res/$m-36-p$p.json ] || python3 /root/r2/granite_ram.py --server $SRV --model $G/$m-Q4_K_M.gguf --label $m-36-p$p \
    --out res/$m-36-p$p.json --cases /root/stephbench-ft/cases_ft36.json --maxc 1500 --ctx 8192 --ubatch 512 --batch 512 \
    --parallel 2 --threads 4 --extra "--cache-ram 0" >> run.log 2>&1
done
for spec in $REF:1 $X:1 $REF:2 $X:2; do
  m=${spec%%:*}; p=${spec##*:}; idle
  echo "$(date +%T) load $(cut -d' ' -f1 /proc/loadavg) $m qa p$p" >> run.log
  [ -f res/$m-qa-p$p.json ] || python3 /root/r2/bench_run.py --server $SRV --model $G/$m-Q4_K_M.gguf --label $m-qa-p$p \
    --out res/$m-qa-p$p.json --cases /root/r2/qa_dev_a52223c.json --maxc 0 --ctx 8192 --ubatch 512 --parallel 2 --threads 4 \
    --extra "--cache-ram 0" --abort-ttft 60 --payload '{"seed": 7}' >> run.log 2>&1
done
echo "$(date +%T) ALLDONE" >> run.log
