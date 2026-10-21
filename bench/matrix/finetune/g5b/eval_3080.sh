#!/bin/bash
# G5b : banc v3 aligné L5 (harnais affiné), juge A7 et Steph Speak Bench sur l'hôte de la 3080, mêmes binaire (CUDA
# 9588757), juge (Qwen3.5 9B 03b74727, judge_x3.py) et contrôles que G5 ; v1.0 et a-sft : runs et verdicts de G5 (liens).
# Ollama arrêté au départ s'il tourne, relancé à la fin par ce script seulement s'il l'a arrêté. Carte partagée : attente
# de 7 Go libres ; serveurs arrêtés par leur PID.
#   eval_3080.sh            DEV (3 graines, jugé), puis TEST une passe (3 graines, jugé), puis Speak Bench
set -u
K=/root/steph-ft/g5b; R=$K/repo; B=/root/steph-ft/llama.cpp/build/bin; T=$R/bench/matrix/v3/tools; J=$K/judge
M=$K/gguf/g5b-sft-Q4_K_M.gguf; QWEN=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf; P=8933
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
wait_free() { until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge $1 ]; do sleep 60; done; }
cd $K; mkdir -p runs verdicts logs speak

wait_free 7000
if systemctl is-active --quiet ollama; then systemctl stop ollama && touch $K/ollama.stopped && note "OLLAMA ARRÊTÉ"; fi
note "DÉPART $(sha256sum $M | cut -c1-16)"

bench() {  # split : 3 graines, commande de chain.sh bench de G5
  for sd in 7 42 123; do
    O=$K/runs/g5b-$1-b$sd.json
    [ -f $O ] && continue
    wait_free 3000
    nice -n 5 python3 $R/bench/matrix/bench_run.py --server $B/llama-server --model $M --label g5b-v3$1-b$sd \
      --cases $R/bench/matrix/v3/harness/$1.json --maxc 0 --port 897${sd: -1} --ngl 99 --abort-ttft 120 \
      --payload "{\"seed\": $sd}" --out $O >> $K/logs/bench-$1.log 2>&1
    note "BANC $1 b$sd rc=$?"
  done
}
judge() {  # split : juge_3080.sh de G5, une carte pour les 3 graines, contrôles 6/6 avant et après
  [ -f $K/verdicts/$1.done ] && return 0
  wait_free 7000
  nice -n 5 $B/llama-server -m $QWEN --host 127.0.0.1 --port $P -c 32768 --parallel 8 -ngl 99 --jinja --no-webui \
    --reasoning-budget 0 > $K/logs/qwen-$P.log 2>&1 < /dev/null &
  SP=$!
  for i in $(seq 180); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
  export JUDGE_PORT=$P PYTHONPATH=$J/jl:$T
  note "JUGE $1 $(sha256sum $QWEN | cut -c1-16) PID $SP"
  (cd $J && python3 j.py $T/judge_validate_v3.py run controls.json $K/verdicts/validate-pre-$1.json > $K/logs/validate-pre-$1.log 2>&1)
  note "VALIDATION $1 avant rc=$? $(tail -1 $K/logs/validate-pre-$1.log)"
  for sd in 7 42 123; do
    r=g5b-$1-b$sd
    for try in 1 2 3; do
      kill -0 $SP 2>/dev/null || { note "ARRÊT : juge $SP mort"; return 1; }
      (cd $J && nice -n 5 python3 judge_x3.py $R/bench/matrix/v3/harness/$1.json $K/verdicts/inv-$r.json $K/runs/$r.json \
        --cache $K/verdicts --threads 8 > $K/logs/j-$r.log 2>&1)
      note "JUGE $r essai $try rc=$? $(tail -1 $K/logs/j-$r.log)"
      tail -1 $K/logs/j-$r.log | grep -q '"erreur": 0' && break
    done
  done
  (cd $J && python3 j.py $T/judge_validate_v3.py run controls.json $K/verdicts/validate-post-$1.json > $K/logs/validate-post-$1.log 2>&1)
  note "VALIDATION $1 après rc=$? $(tail -1 $K/logs/validate-post-$1.log)"
  kill $SP; sleep 5; touch $K/verdicts/$1.done
}
speak() {  # speak.sh de G5 : protocole steph, test, température 0, --cache-ram 0
  S=$K/speak/g5b; mkdir -p $S; wait_free 2000
  nice -n 5 $B/llama-server -m $M --host 127.0.0.1 --port 8895 -c 4096 -ngl 99 --no-webui --jinja --parallel 1 --cache-ram 0 \
    > $K/logs/speak-server.log 2>&1 < /dev/null &
  SP=$!
  for i in $(seq 60); do curl -sf http://127.0.0.1:8895/health >/dev/null && break; sleep 1; done
  for spec in fr:train_system_prompt.txt en:train_system_prompt.en.txt; do
    lang=${spec%%:*}
    ls $S/*_g5b-steph_${lang}_test.json >/dev/null 2>&1 && continue
    python3 $R/benchmark/run.py --base-url http://127.0.0.1:8895/v1 --model steph --label g5b-steph --out $S --quiet \
      --hardware "RTX 3080 CUDA" --notes "G5b, Q4_K_M" --lang $lang --split test \
      --system-prompt-file $R/bench/matrix/finetune/${spec#*:} >> $K/logs/speak.log 2>&1
    note "SPEAK $lang rc=$?"
  done
  kill $SP
}

bench dev && judge dev || exit 1
bench test && judge test || exit 1
speak
if [ -f $K/ollama.stopped ]; then systemctl start ollama && rm $K/ollama.stopped && note "OLLAMA RELANCÉ"; fi
note "FIN"
