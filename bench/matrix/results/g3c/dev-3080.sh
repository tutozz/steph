#!/bin/bash
# G3c, contrôle rapide sur DEV (pas de décision) : banc v3 dev générique aligné L5 (e96d54d4), graine de banc 42, 3080 CUDA
# llama.cpp 9588757 (celui de G3b), bench_run.py au HEAD, 2 couloirs ; puis juge A7 (Qwen3.5 9B 03b74727, judge_x3.py,
# contrôles 6/6 avant et après) sur les réponses reaches_model. Ollama arrêté au début, relancé à la fin.
#   dev-3080.sh <modèle>...   (GGUF attendus dans /dev/shm/g3c/<modèle>.gguf)
set -u
W=/root/steph-ft/g3c/ft; R=$W/repo; H=$W/dev.generic.json; SRV=/root/steph-ft/llama.cpp/build/bin/llama-server
J=/root/steph-ft/g3/eval/judge; QW=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf; T=$R/bench/matrix/v3/tools
note() { echo "$(date '+%d %H:%M') $*" >> $W/dev.done; }
mkdir -p $W/runs $W/verdicts $W/logs; cd $W
[ "$(sha256sum $H | cut -c1-16)" = e96d54d4f9017880 ] || { note "ARRÊT : harnais dev"; exit 1; }
systemctl is-active -q ollama && { systemctl stop ollama; note "ollama arrêté par G3c"; }
lane() {  # lane <port> <modèle>...
  local port=$1; shift
  for m in "$@"; do
    OUT=$W/runs/$m-dev-b42.json; [ -f $OUT ] && continue
    while [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)" -lt 4000 ]; do sleep 60; done
    nice -n 5 python3 $R/bench/matrix/bench_run.py --server $SRV --model /dev/shm/g3c/$m.gguf --label g3c-$m-v3dev-l5-cuda-b42 \
      --cases $H --maxc 0 --port $port --ngl 99 --abort-ttft 120 --payload '{"seed": 42}' --out $OUT >> $W/logs/lane-$port.log 2>&1
    note "RUN $m rc=$? $(sha256sum $OUT 2>/dev/null | cut -c1-16)"
  done
}
A=(); B=(); i=0
for m in "$@"; do if [ $((i % 2)) = 0 ]; then A+=($m); else B+=($m); fi; i=$((i + 1)); done
lane 8971 "${A[@]}" & lane 8972 "${B[@]}" & wait
until [ "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l)" -eq 0 ]; do sleep 10; done
nice -n 5 $SRV -m $QW --host 127.0.0.1 --port 8996 -c 16384 --parallel 4 -ngl 99 --jinja --no-webui --reasoning-budget 0 \
  > $W/logs/qwen.log 2>&1 < /dev/null &
SP=$!
for i in $(seq 180); do curl -sf http://127.0.0.1:8996/health > /dev/null && break; sleep 2; done
note "juge $(sha256sum $QW | cut -c1-16)"
export JUDGE_PORT=8996 PYTHONPATH=$J/jl:$T
cd $J
python3 j.py $T/judge_validate_v3.py run controls.json $W/verdicts/validate-pre.json > $W/logs/validate-pre.log 2>&1
note "VALIDATION avant rc=$? $(tail -1 $W/logs/validate-pre.log)"
for m in "$@"; do
  r=$m-dev-b42
  python3 judge_x3.py $H $W/verdicts/inv-$r.json $W/runs/$r.json --cache $W/verdicts --threads 8 > $W/logs/j-$r.log 2>&1
  note "JUGE $r rc=$? $(tail -1 $W/logs/j-$r.log)"
done
python3 j.py $T/judge_validate_v3.py run controls.json $W/verdicts/validate-post.json > $W/logs/validate-post.log 2>&1
note "VALIDATION après rc=$? $(tail -1 $W/logs/validate-post.log)"
kill $SP; sleep 5; systemctl start ollama; note "ollama relancé, FIN"
