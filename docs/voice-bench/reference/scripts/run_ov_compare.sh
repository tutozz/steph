#!/usr/bin/env bash
set -uo pipefail
ENGINE=/root/stephbench/bin/llama-b11200
VENV=/root/stephbench/venv/bin/python
OUT=/root/stephbench/results
LOG=/root/stephbench/logs/driver_ovcompare.log
GGUF=/mnt/backup-hdd/stephbench-tmp/models/Qwen3-1.7B-Q4_K_M.gguf
OVDIR=/mnt/backup-hdd/stephbench-tmp/models/Qwen3-1.7B-int4-ov

declare -A CPUS=( [N2]="0,1,6,7" [N3]="0,1,2,3,6,7,8,9" )
declare -A THREADS=( [N2]=2 [N3]=4 )
declare -A MEM=( [N2]="4G" [N3]="8G" )

wait_for_load() {
  local tries=0
  while true; do
    ld1=$(cut -d' ' -f1 /proc/loadavg)
    over=$(awk -v l="$ld1" 'BEGIN{print (l>4)?1:0}')
    if [ "$over" = "1" ]; then
      echo "charge $ld1 > 4, attente 30s" | tee -a "$LOG"
      sleep 30
      tries=$((tries+1))
      [ $tries -gt 10 ] && break
    else
      break
    fi
  done
}

for level in N2 N3; do
  # --- llama.cpp GGUF ---
  label="${level}_qwen17_gguf"
  out="$OUT/${label}.json"
  if [ ! -s "$out" ]; then
    wait_for_load
    echo "=== $(date -Iseconds) DEBUT $label ===" | tee -a "$LOG"
    systemd-run --scope --quiet -p AllowedCPUs=${CPUS[$level]} -p MemoryMax=${MEM[$level]} \
      nice -n 19 "$VENV" /root/stephbench/scripts/steph_bench.py \
      --model "$GGUF" --engine-dir "$ENGINE" --threads "${THREADS[$level]}" \
      --port 8813 --maxc 6000 --label "$label" --out "$out" >>"$LOG" 2>&1
    echo "=== $(date -Iseconds) FIN_COMBO $label ===" | tee -a "$LOG"
    pkill -9 -f "llama-server.*--port 8813" 2>/dev/null || true
    sleep 2
  fi

  # --- OpenVINO int4 ---
  label="${level}_qwen17_ov"
  out="$OUT/${label}.json"
  if [ ! -s "$out" ]; then
    wait_for_load
    echo "=== $(date -Iseconds) DEBUT $label ===" | tee -a "$LOG"
    systemd-run --scope --quiet -p AllowedCPUs=${CPUS[$level]} -p MemoryMax=${MEM[$level]} \
      nice -n 19 "$VENV" /root/stephbench/scripts/ov_bench.py \
      --model-dir "$OVDIR" --threads "${THREADS[$level]}" \
      --maxc 6000 --label "$label" --out "$out" --no-think >>"$LOG" 2>&1
    echo "=== $(date -Iseconds) FIN_COMBO $label ===" | tee -a "$LOG"
    sleep 2
  fi
done

echo "ALL_DONE_ovcompare" | tee -a "$LOG"
