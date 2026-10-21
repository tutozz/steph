#!/bin/bash
# CONTROL : le fichier retenu off-ple3 (b47196ac, quantifié sur la 3060) reproduit-il le run banqué g4-off-ple3-test-b7 (cddf1f1a, 3080) ?
set -u
C=/root/steph-ft/control; W=/root/steph-ft/g4
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader > $C/gpu-before.txt
systemctl stop ollama; echo "$(date +%T) ollama arrêté" >> $C/run.log
nice -n 5 python3 $W/repo/bench/matrix/bench_run.py --server /root/steph-ft/llama.cpp/build/bin/llama-server \
  --model $C/off-ple3.gguf --label control-off-ple3-b47196ac-v3test-cuda-b7 --cases $W/harness/test.generic.json \
  --maxc 0 --port 8991 --ngl 99 --abort-ttft 120 --payload "{\"seed\": 7}" --out $C/control-off-ple3-test-b7.json >> $C/run.log 2>&1
echo "$(date +%T) bench rc=$?" >> $C/run.log
systemctl start ollama; echo "$(date +%T) ollama relancé $(systemctl is-active ollama)" >> $C/run.log
