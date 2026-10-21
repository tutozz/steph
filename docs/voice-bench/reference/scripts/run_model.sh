#!/usr/bin/env bash
# Lance la matrice de niveaux pour un modele donne, dans des scopes cgroup dedies.
set -uo pipefail
MODEL_NAME="$1"
MODEL_PATH="$2"
EXTRA_FULL_N3="${3:-0}"
ENGINE=/root/stephbench/bin/llama-b11200
VENV=/root/stephbench/venv/bin/python
OUT=/root/stephbench/results
LOG=/root/stephbench/logs/driver_${MODEL_NAME}.log
PORT=8812

declare -A CPUS=( [N1]="0,6" [N2]="0,1,6,7" [N3]="0,1,2,3,6,7,8,9" [N4]="0,1,2,3,4,5,6,7,8,9,10,11" )
declare -A THREADS=( [N1]=2 [N2]=2 [N3]=4 [N4]=6 )
declare -A MEM=( [N1]=4G [N2]=4G [N3]=8G [N4]=7G )
declare -A QUOTAOPT=( [N1]="-p CPUQuota=100%" [N2]="" [N3]="" [N4]="" )

wait_for_load() {
  local tries=0
  while true; do
    ld1=$(cut -d' ' -f1 /proc/loadavg)
    over=$(awk -v l="$ld1" 'BEGIN{print (l>4)?1:0}')
    if [ "$over" = "1" ]; then
      echo "charge $ld1 > 4, attente 30s" | tee -a "$LOG"
      sleep 30
      tries=$((tries+1))
      [ $tries -gt 10 ] && { echo "charge toujours haute apres 5min d'attente, on continue quand meme" | tee -a "$LOG"; break; }
    else
      break
    fi
  done
}

run_combo() {
  local level="$1" maxc="$2" full="$3"
  local label="${level}_${MODEL_NAME}_maxc${maxc}"
  [ "$full" = "1" ] && label="${label}_full29"
  local out="$OUT/${label}.json"
  if [ -s "$out" ]; then
    echo "SKIP $label (deja fait)" | tee -a "$LOG"
    return
  fi
  wait_for_load
  echo "=== $(date -Iseconds) DEBUT $label charge=$(cut -d' ' -f1 /proc/loadavg) ===" | tee -a "$LOG"
  local fullflag=""
  [ "$full" = "1" ] && fullflag="--full"
  # shellcheck disable=SC2086
  systemd-run --scope --quiet -p AllowedCPUs=${CPUS[$level]} ${QUOTAOPT[$level]} -p MemoryMax=${MEM[$level]} \
    nice -n 19 "$VENV" /root/stephbench/scripts/steph_bench.py \
    --model "$MODEL_PATH" --engine-dir "$ENGINE" --threads "${THREADS[$level]}" \
    --port "$PORT" --maxc "$maxc" $fullflag --label "$label" --out "$out" >>"$LOG" 2>&1
  echo "=== $(date -Iseconds) FIN_COMBO $label ===" | tee -a "$LOG"
  pkill -9 -f "llama-server.*--port $PORT" 2>/dev/null || true
  sleep 2
}

for level in N1 N2 N3 N4; do
  run_combo "$level" 6000 0
  if [ "$level" = "N1" ] || [ "$level" = "N2" ]; then
    run_combo "$level" 1500 0
  fi
  if [ "$level" = "N3" ] && [ "$EXTRA_FULL_N3" = "1" ]; then
    run_combo "$level" 6000 1
  fi
done

echo "ALL_DONE_${MODEL_NAME}" | tee -a "$LOG"
