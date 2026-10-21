#!/bin/bash
# X4 sur xeon : réétiquetage 27B (progression + flux, résumés EN, résumés FR) sur les cœurs 8-31,
# détail K3 régénéré au 9B sur 0-7, puis rejets K3 du détail rejugés au 27B, puis assemblage.
# La boucle X1 (tout processus dont le cwd est sous /root/steph-ft/loop) a priorité : tant qu'elle
# tourne, les deux serveurs sont gelés (SIGSTOP), jamais les siens ; chaque gel est journalisé.
set -u
W=/root/steph-ft/x4
cd $W
NAT=/root/steph-ft/llama/llama-b11205
export LD_LIBRARY_PATH=$NAT:/root/steph-ft/vendor/lib
M=/root/steph-ft/x4a/models
A="env PYTHONPATH=code/src python3 code/bench/matrix/finetune/x4_relabel.py"
mkdir -p logs labels final

loop_busy() {
  local p c
  for p in /proc/[0-9]*; do
    c=$(readlink "$p/cwd" 2>/dev/null) || continue
    case "$c" in /root/steph-ft/loop*) return 0 ;; esac
  done
  return 1
}

echo "$(date +%T) attente de la boucle X1"
calm=0
while [ $calm -lt 5 ]; do if loop_busy; then calm=0; else calm=$((calm+1)); fi; sleep 60; done
echo "$(date +%T) départ"

[ -f tasks.jsonl ] || $A build --final /root/steph-ft/data/final --hashes /root/steph-ft/x4a/hashes --out tasks.jsonl > logs/build.log 2>&1

systemd-run --scope --quiet -p AllowedCPUs=0-7 -p MemoryMax=64G nice -n 19 \
  $NAT/llama-server -m $M/Qwen3.5-9B-Q4_K_M.gguf --host 127.0.0.1 --port 8961 -c 8192 -t 8 \
  --jinja --no-webui --parallel 1 -ub 512 > logs/srv9.log 2>&1 < /dev/null &
S9=$!
systemd-run --scope --quiet -p AllowedCPUs=8-31 -p MemoryMax=64G nice -n 19 \
  $NAT/llama-server -m $M/Qwen3.5-27B-Q4_K_M.gguf --host 127.0.0.1 --port 8960 -c 8192 -t 24 \
  --jinja --no-webui --parallel 1 -ub 512 > logs/srv27b.log 2>&1 < /dev/null &
S27=$!
echo "$S9 $S27" > logs/servers.pid
echo "$(date +%T) serveurs $S9 $S27"
until curl -s 127.0.0.1:8961/health | grep -q ok && curl -s 127.0.0.1:8960/health | grep -q ok; do sleep 5; done

(
  frozen=0
  while kill -0 $S27 2>/dev/null; do
    if loop_busy; then
      [ $frozen = 0 ] && { kill -STOP $S9 $S27 2>/dev/null; echo "$(date +%s) STOP" >> logs/pauses.log; frozen=1; }
    else
      [ $frozen = 1 ] && { kill -CONT $S9 $S27 2>/dev/null; echo "$(date +%s) CONT" >> logs/pauses.log; frozen=0; }
    fi
    sleep 10
  done
) &

(
  $A label --tasks tasks.jsonl --task detail --port 8961 --model-tag 9b --out labels/detail.jsonl > logs/detail.log 2>&1
  touch logs/detail.done
  kill -CONT $S9 2>/dev/null; kill $S9
) &
for t in progress en_summary fr_summary; do
  $A label --tasks tasks.jsonl --task $t --port 8960 --model-tag 27b --out labels/$t.jsonl > logs/$t.log 2>&1
  echo "$(date +%T) $t fait"
done
until [ -f logs/detail.done ]; do sleep 30; done
$A judge --tasks tasks.jsonl --labels labels/detail.jsonl --port 8960 --out labels/detail-judge27.jsonl > logs/judge.log 2>&1
kill -CONT $S27 2>/dev/null; kill $S27
$A assemble --final /root/steph-ft/data/final --tasks tasks.jsonl --labels labels/{detail,progress,en_summary,fr_summary}.jsonl \
  --judge labels/detail-judge27.jsonl --out final > logs/assemble.json 2> logs/assemble.err
( cd final && sha256sum *.jsonl > SHA256SUMS )
echo "$(date +%T) X4 terminé"
