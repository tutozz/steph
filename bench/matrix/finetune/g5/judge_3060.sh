#!/bin/bash
# G5 : juge A7 (Qwen3.5 9B Q4_K_M 03b74727, judge_lib A7 e52813e1, judge_x3.py) sur l'hôte de la 3060, Vulkan b11205.
# Runs copiés depuis la 3080 dans runs/ ; contrôles 6/6 FR et EN avant et après ; juge arrêté par son PID.
#   judge_3060.sh <dev|test> <graines "7 42"> <modèle>...
set -u
S=$1; SEEDS=$2; shift 2
W=/mnt/backup-hdd/stephbench-tmp/g5j; J=$W/judge; T=$W/repo/bench/matrix/v3/tools; P=8993
LB=/root/stephbench-matrix/bin/vulkan/llama-b11205; M=/mnt/backup-hdd/stephbench-tmp/models/Qwen3.5-9B-Q4_K_M.gguf
export LD_LIBRARY_PATH=$LB JUDGE_PORT=$P PYTHONPATH=$J/jl:$T
note() { echo "$(date '+%d %T') $*" >> $W/judge.done; }
cd $J
while [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]; do sleep 30; done
nice -n 19 $LB/llama-server -m $M --host 127.0.0.1 --port $P -c 32768 --parallel 8 -ngl 99 --jinja --no-webui --reasoning-budget 0 \
  > $W/logs/qwen-$P.log 2>&1 < /dev/null &
SP=$!
for i in $(seq 180); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
note "juge $(sha256sum $M | cut -c1-16) PID $SP"
tag=$S-$(date +%H%M)
python3 j.py $T/judge_validate_v3.py run controls.json $W/verdicts/validate-pre-$tag.json > $W/logs/validate-pre-$tag.log 2>&1
note "VALIDATION avant rc=$? $(tail -1 $W/logs/validate-pre-$tag.log)"
for m in "$@"; do
  for sd in $SEEDS; do
    r=$m-$S-b$sd
    until [ -f $W/runs/$r.json ]; do sleep 60; done
    [ -f $W/verdicts/inv-$r.json.done ] && continue
    for try in 1 2 3; do  # reprise : judge_x3 rejuge les erreurs ; serveur mort (tué par un tiers une fois) = arrêt
      kill -0 $SP 2>/dev/null || { note "ARRÊT : juge $SP mort"; exit 1; }
      nice -n 19 python3 judge_x3.py $W/repo/bench/matrix/v3/harness/$S.json $W/verdicts/inv-$r.json $W/runs/$r.json \
        --cache $W/verdicts --threads 8 > $W/logs/j-$r.log 2>&1
      note "JUGE $r essai $try rc=$? $(tail -1 $W/logs/j-$r.log)"
      tail -1 $W/logs/j-$r.log | grep -q '"erreur": 0' && { touch $W/verdicts/inv-$r.json.done; break; }
    done
  done
done
python3 j.py $T/judge_validate_v3.py run controls.json $W/verdicts/validate-post-$tag.json > $W/logs/validate-post-$tag.log 2>&1
note "VALIDATION après rc=$? $(tail -1 $W/logs/validate-post-$tag.log)"
kill $SP; note "FIN juge"
