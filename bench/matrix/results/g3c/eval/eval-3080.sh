#!/bin/bash
# G3c TEST, une seule passe : banc v3 test aligné L5, 3 graines, 4 modèles dans la même session sur la 3080 (CUDA, llama.cpp
# 9588757 de G3b et G4b), bench_run.py au commit archivé dans repo/ ; Gemma sur le générique 8d90a662, v1.0 sur l'affiné
# 705fdcb9. Puis juge A7 (Qwen3.5 9B 03b74727, judge_x3.py de G3, 2 passes, cache neuf) sur les 12 runs, contrôles 6/6
# avant et après, jusqu'à 3 essais par run en erreur de juge. Ollama arrêté au départ s'il tourne, relancé à la fin
# seulement si ce script l'a arrêté. Carte partagée : attente de mémoire libre, serveurs arrêtés par leur PID.
#   eval-3080.sh   (GGUF : /dev/shm/g3c-eval/<modèle>.gguf ; v1.0 sur disque)
set -u
W=/root/steph-ft/g3c/eval; R=$W/repo; B=/root/steph-ft/llama.cpp/build/bin; T=$R/bench/matrix/v3/tools
J=/root/steph-ft/g3/eval/judge; QW=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf; P=8936
declare -A GG=([g3c]=/dev/shm/g3c-eval/g3c.gguf [g3b]=/dev/shm/g3c-eval/g3b.gguf [gemma-raw]=/dev/shm/g3c-eval/gemma-raw.gguf
               [v10]=/root/steph-ft/r1/gguf/steph-speak-granite-4.0-h-350M-dpo-v1.0-Q4_K_M.gguf)
declare -A SHA=([g3c]=3e36aeed1503032f [g3b]=eb6e76076b819d9e [gemma-raw]=fa401b55b07ee70a [v10]=45414bd2)
declare -A HH=([g3c]=test.generic [g3b]=test.generic [gemma-raw]=test.generic [v10]=test)
note() { echo "$(date '+%d %H:%M:%S') $*" >> $W/run.done; }
wait_free() { until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)" -ge $1 ]; do sleep 60; done; }
cd $W; mkdir -p runs verdicts logs
trap '[ -f $W/ollama.stopped ] && systemctl start ollama && rm $W/ollama.stopped && note "OLLAMA RELANCÉ"' EXIT
[ "$(sha256sum harness/test.json | cut -c1-16)" = 705fdcb9e5784e7d ] || { note "ARRÊT : harnais affiné"; exit 1; }
[ "$(sha256sum harness/test.generic.json | cut -c1-16)" = 8d90a662aac4cf24 ] || { note "ARRÊT : harnais générique"; exit 1; }
for m in "${!GG[@]}"; do
  s=$(sha256sum ${GG[$m]} | cut -c1-16); note "GGUF $m $s"
  case $s in ${SHA[$m]}*) ;; *) note "ARRÊT : GGUF $m"; exit 1;; esac
done
wait_free 7000
if systemctl is-active --quiet ollama; then systemctl stop ollama && touch $W/ollama.stopped && note "OLLAMA ARRÊTÉ"; fi

# graine 7 d'abord (la formulation sur xeon n'attend qu'elle), G3c et G3b en tête
JOBS="g3c:7 g3b:7 gemma-raw:7 v10:7 g3c:42 g3b:42 gemma-raw:42 v10:42 g3c:123 g3b:123 gemma-raw:123 v10:123"
printf '%s\n' $JOBS > $W/jobs.q
lane() {
  local port=$1 job m sd OUT
  while :; do
    job=$(flock $W/jobs.q.lock sh -c "head -1 $W/jobs.q; sed -i 1d $W/jobs.q")
    [ -z "$job" ] && break
    m=${job%%:*}; sd=${job##*:}; OUT=$W/runs/$m-test-b$sd.json
    [ -f $OUT ] && continue
    wait_free 4000
    nice -n 5 python3 $R/bench/matrix/bench_run.py --server $B/llama-server --model ${GG[$m]} --label g3c-$m-v3test-l5-cuda-b$sd \
      --cases $W/harness/${HH[$m]}.json --maxc 0 --port $port --ngl 99 --abort-ttft 120 --payload "{\"seed\": $sd}" \
      --out $OUT >> $W/logs/lane-$port.log 2>&1
    note "BANC $m b$sd rc=$? $(sha256sum $OUT 2>/dev/null | cut -c1-16)"
  done
}
lane 8961 & lane 8962 & wait
for m in g3c g3b gemma-raw v10; do for sd in 7 42 123; do [ -f runs/$m-test-b$sd.json ] || { note "ARRÊT : run $m b$sd manquant"; exit 1; }; done; done

wait_free 7000
nice -n 5 $B/llama-server -m $QW --host 127.0.0.1 --port $P -c 16384 --parallel 4 -ngl 99 --jinja --no-webui \
  --reasoning-budget 0 > $W/logs/qwen.log 2>&1 < /dev/null &
SP=$!
for i in $(seq 180); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
note "JUGE $(sha256sum $QW | cut -c1-16) PID $SP"
export JUDGE_PORT=$P PYTHONPATH=$J/jl:$T
(cd $J && python3 j.py $T/judge_validate_v3.py run controls.json $W/verdicts/validate-pre.json > $W/logs/validate-pre.log 2>&1)
note "VALIDATION avant rc=$? $(tail -1 $W/logs/validate-pre.log)"
for sd in 7 42 123; do for m in g3c g3b gemma-raw v10; do
  r=$m-test-b$sd
  for try in 1 2 3; do
    kill -0 $SP 2>/dev/null || { note "ARRÊT : juge $SP mort"; exit 1; }
    (cd $J && nice -n 5 python3 judge_x3.py $W/harness/${HH[$m]}.json $W/verdicts/inv-$r.json $W/runs/$r.json \
      --cache $W/verdicts --threads 8 > $W/logs/j-$r.log 2>&1)
    note "JUGE $r essai $try rc=$? $(tail -1 $W/logs/j-$r.log)"
    tail -1 $W/logs/j-$r.log | grep -q '"erreur": 0' && break
  done
done; done
(cd $J && python3 j.py $T/judge_validate_v3.py run controls.json $W/verdicts/validate-post.json > $W/logs/validate-post.log 2>&1)
note "VALIDATION après rc=$? $(tail -1 $W/logs/validate-post.log)"
kill $SP; sleep 5
note "FIN"
