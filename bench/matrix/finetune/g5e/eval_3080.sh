#!/bin/bash
# G5e : banc v3 aligné L5 (harnais affiné), juge A7 et Steph Speak Bench sur l'hôte de la 3080, mêmes binaire (CUDA
# 9588757), juge (Qwen3.5 9B 03b74727, judge_x3.py, contrôles 6/6 avant et après) et commandes que eval_3080.sh de G5c.
# a-sft est regénéré dans cette session et comparé réponse par réponse aux runs de G5c (eux-mêmes égaux à ceux de G5) :
# identique, ses verdicts A7 servent ; sinon il est jugé ici. G5c n'est pas regénéré : ses runs et verdicts sont repris.
# Ollama arrêté au départ s'il tourne, relancé à la fin seulement si ce script l'a arrêté. Serveurs arrêtés par leur PID.
#   eval_3080.sh dev    DEV 3 graines, juge A7, g5_eval.py contre a-sft et G5c
#   eval_3080.sh test   TEST une passe 3 graines, juge A7, Speak Bench, g5_eval.py contre a-sft et G5c
set -u
STEP=$1
K=/root/steph-ft/g5e; R=$K/repo; B=/root/steph-ft/llama.cpp/build/bin; T=$R/bench/matrix/v3/tools; J=$K/judge
C=/root/steph-ft/g5c; QWEN=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf; P=8934
declare -A GG=([g5e]=$K/gguf/g5e-a-sft-Q4_K_M.gguf [a-sft]=/root/steph-ft/g5/gguf/g5-a-sft-Q4_K_M.gguf)
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
wait_free() { until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge $1 ]; do sleep 60; done; }
cd $K; mkdir -p runs verdicts vall logs speak eval empty
[ -d $J ] || cp -r $C/judge $J
trap '[ -f $K/ollama.stopped ] && systemctl start ollama && rm $K/ollama.stopped && note "OLLAMA RELANCÉ"' EXIT

wait_free 7000
if systemctl is-active --quiet ollama; then systemctl stop ollama && touch $K/ollama.stopped && note "OLLAMA ARRÊTÉ"; fi
for m in g5e a-sft; do note "GGUF $m $(sha256sum ${GG[$m]} | cut -c1-16)"; done

bench() {  # modèle split : 3 graines, commande de eval_3080.sh de G5c
  for sd in 7 42 123; do
    O=$K/runs/$1-$2-b$sd.json
    [ -f $O ] && continue
    wait_free 3000
    nice -n 5 python3 $R/bench/matrix/bench_run.py --server $B/llama-server --model ${GG[$1]} --label g5e-$1-v3$2-b$sd \
      --cases $R/bench/matrix/v3/harness/$2.json --maxc 0 --port 898${sd: -1} --ngl 99 --abort-ttft 120 \
      --payload "{\"seed\": $sd}" --out $O >> $K/logs/bench-$2.log 2>&1
    note "BANC $1 $2 b$sd rc=$?"
  done
}
same() {  # modèle split : 0 si les 3 runs de cette session ont les réponses des runs de G5c
  for sd in 7 42 123; do
    python3 -c "import json,sys; o=lambda p: {r['id']: r.get('out') for r in json.load(open(p))['rows']}; sys.exit(o(sys.argv[1]) != o(sys.argv[2]))" \
      $K/runs/$1-$2-b$sd.json $C/runs/$1-$2-b$sd.json || return 1
  done
}
judge() {  # split modèles... : juge A7 de G5c, une carte, contrôles 6/6 avant et après
  S=$1; shift
  [ -f $K/verdicts/$S.done ] && return 0
  wait_free 7000
  nice -n 5 $B/llama-server -m $QWEN --host 127.0.0.1 --port $P -c 32768 --parallel 8 -ngl 99 --jinja --no-webui \
    --reasoning-budget 0 > $K/logs/qwen-$P.log 2>&1 < /dev/null &
  SP=$!
  for i in $(seq 180); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
  export JUDGE_PORT=$P PYTHONPATH=$J/jl:$T
  note "JUGE $S $* $(sha256sum $QWEN | cut -c1-16) PID $SP"
  (cd $J && python3 j.py $T/judge_validate_v3.py run controls.json $K/verdicts/validate-pre-$S.json > $K/logs/validate-pre-$S.log 2>&1)
  note "VALIDATION $S avant rc=$? $(tail -1 $K/logs/validate-pre-$S.log)"
  for m in "$@"; do for sd in 7 42 123; do
    r=$m-$S-b$sd
    for try in 1 2 3; do
      kill -0 $SP 2>/dev/null || { note "ARRÊT : juge $SP mort"; return 1; }
      (cd $J && nice -n 5 python3 judge_x3.py $R/bench/matrix/v3/harness/$S.json $K/verdicts/inv-$r.json $K/runs/$r.json \
        --cache $K/verdicts --threads 8 > $K/logs/j-$r.log 2>&1)
      note "JUGE $r essai $try rc=$? $(tail -1 $K/logs/j-$r.log)"
      tail -1 $K/logs/j-$r.log | grep -q '"erreur": 0' && break
    done
  done; done
  (cd $J && python3 j.py $T/judge_validate_v3.py run controls.json $K/verdicts/validate-post-$S.json > $K/logs/validate-post-$S.log 2>&1)
  note "VALIDATION $S après rc=$? $(tail -1 $K/logs/validate-post-$S.log)"
  kill $SP; sleep 5; touch $K/verdicts/$S.done
}
split() {  # split : bancs G5e et a-sft, a-sft comparé à G5c, juge A7, runs et verdicts de G5c liés
  for m in g5e a-sft; do bench $m $1; done
  todo=g5e
  if same a-sft $1; then
    note "IDENTIQUE a-sft $1 : réponses égales aux runs de G5c, verdicts A7 de G5c"
    for sd in 7 42 123; do ln -sfn $(readlink -f $C/vall/inv-a-sft-$1-b$sd.json) $K/vall/inv-a-sft-$1-b$sd.json; done
  else
    note "DIFFÉRENT a-sft $1 : jugé dans cette session"; todo="$todo a-sft"
  fi
  judge $1 $todo || return 1
  for m in $todo; do for sd in 7 42 123; do ln -sfn $K/verdicts/inv-$m-$1-b$sd.json $K/vall/; done; done
  for sd in 7 42 123; do
    ln -sfn $(readlink -f $C/vall/inv-g5c-$1-b$sd.json) $K/vall/inv-g5c-$1-b$sd.json
    ln -sfn $C/runs/g5c-$1-b$sd.json $K/runs/g5c-$1-b$sd.json
  done
}
evaluate() {  # split : g5_eval.py (python du venv : numpy) sur G5e, a-sft, G5c
  PYTHONPATH=$T:$R/bench/matrix/results/finetune/loop/round-3/r3t2p3:$R/bench/matrix/finetune \
    /root/steph-ft/venv/bin/python $R/bench/matrix/results/g5/g5_eval.py $1 $K/runs $K/vall $K/empty $R/bench/matrix/v3/harness \
    $K/eval/g5e-eval-$1.json > $K/logs/eval-$1.out 2> $K/logs/eval-$1.err
  note "EVAL $1 rc=$?"
}
speak() {  # speak.sh de G5 : protocole steph, test, température 0, --cache-ram 0
  for m in g5e a-sft; do
    S=$K/speak/$m; mkdir -p $S; wait_free 2000
    nice -n 5 $B/llama-server -m ${GG[$m]} --host 127.0.0.1 --port 8896 -c 4096 -ngl 99 --no-webui --jinja --parallel 1 \
      --cache-ram 0 > $K/logs/speak-server.log 2>&1 < /dev/null &
    SP=$!
    for i in $(seq 60); do curl -sf http://127.0.0.1:8896/health >/dev/null && break; sleep 1; done
    for spec in fr:train_system_prompt.txt en:train_system_prompt.en.txt; do
      lang=${spec%%:*}
      ls $S/*_$m-steph_${lang}_test.json >/dev/null 2>&1 && continue
      python3 $R/benchmark/run.py --base-url http://127.0.0.1:8896/v1 --model steph --label $m-steph --out $S --quiet \
        --hardware "RTX 3080 CUDA" --notes "G5e, Q4_K_M" --lang $lang --split test \
        --system-prompt-file $R/bench/matrix/finetune/${spec#*:} >> $K/logs/speak.log 2>&1
      note "SPEAK $m $lang rc=$?"
    done
    kill $SP; sleep 3
  done
}

case $STEP in
  dev) split dev && evaluate dev ;;
  test) split test && evaluate test && speak ;;
  *) echo "usage : eval_3080.sh dev|test" >&2; exit 2 ;;
esac
note "FIN $STEP"
