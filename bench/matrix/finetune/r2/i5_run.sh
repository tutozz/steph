#!/bin/bash
# R2 : i5-7200U, réglages de production (cpu.toml : -c 8192 --parallel 2 -t 4 --cache-ram 0 -ub 512 -b 512), b11205.
# Une mesure à la fois, machine au repos avant chaque passe, v1.0 et R2 alternés, deux passes chacun.
# 36 cas (cases_ft36, granite_ram.py, même harnais que Q3 et le tour 2), puis 90 questions dev v3 à froid (a52223c).
cd /root/r2; mkdir -p res
SRV=/root/stephbench-g2/bin/llama-b11205/llama-server; G=/root/x1judge2/gguf
idle() { while [ "$(LC_ALL=C awk '{print ($1<0.3)}' /proc/loadavg)" != 1 ]; do sleep 10; done; }
for spec in v10:r1:1 r2:r2:1 v10:r1:2 r2:r2:2; do
  IFS=: read m f p <<< "$spec"; idle
  echo "$(date +%T) load $(cut -d' ' -f1 /proc/loadavg) $m 36 p$p" >> run.log
  python3 granite_ram.py --server $SRV --model $G/$f-Q4_K_M.gguf --label $m-36-p$p --out res/$m-36-p$p.json \
    --cases /root/stephbench-ft/cases_ft36.json --maxc 1500 --ctx 8192 --ubatch 512 --batch 512 --parallel 2 --threads 4 \
    --extra "--cache-ram 0" >> run.log 2>&1
done
for spec in v10:r1:1 r2:r2:1 v10:r1:2 r2:r2:2; do
  IFS=: read m f p <<< "$spec"; idle
  echo "$(date +%T) load $(cut -d' ' -f1 /proc/loadavg) $m qa p$p" >> run.log
  python3 bench_run.py --server $SRV --model $G/$f-Q4_K_M.gguf --label $m-qa-p$p --out res/$m-qa-p$p.json \
    --cases qa_dev_a52223c.json --maxc 0 --ctx 8192 --ubatch 512 --parallel 2 --threads 4 --extra "--cache-ram 0" \
    --abort-ttft 60 --payload '{"seed": 7}' >> run.log 2>&1
done
echo "$(date +%T) ALLDONE" >> run.log
