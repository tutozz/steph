#!/bin/bash
# G3b : second juge A7 sur la 3080 (même Qwen3.5 9B Q4_K_M 03b74727, même judge_lib A7, même judge_x3.py, contrôles 6/6
# avant et après), harnais L5 ; la 3060 juge le brut et G3 SFT 42, celle-ci G3b et v1.0. Relance Ollama à la fin.
#   judge-3080.sh <modèle>:<harnais test|test.generic> ...
set -u
W=/root/steph-ft/g3b; J=/root/steph-ft/g3/eval/judge; P=8996
M=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf; SRV=/root/steph-ft/llama.cpp/build/bin/llama-server; T=$W/repo/bench/matrix/v3/tools
note() { echo "$(date +%T) $*" >> $W/judge.done; }
mkdir -p $W/verdicts; cd $J
until [ "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l)" -eq 0 ]; do sleep 10; done
note "juge $(sha256sum $M | cut -c1-16)"
nice -n 5 $SRV -m $M --host 127.0.0.1 --port $P -c 16384 --parallel 4 -ngl 99 --jinja --no-webui --reasoning-budget 0 > $W/logs/qwen.log 2>&1 < /dev/null &
SP=$!
for i in $(seq 180); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
export JUDGE_PORT=$P PYTHONPATH=$J/jl:$T
python3 j.py $T/judge_validate_v3.py run controls.json $W/verdicts/validate-pre.json > $W/logs/validate-pre.log 2>&1; note "VALIDATION avant rc=$? $(tail -1 $W/logs/validate-pre.log)"
for mh in "$@"; do
  m=${mh%%:*}; h=${mh##*:}
  for sd in 7 42 123; do
    r=$m-test-b$sd
    python3 judge_x3.py $W/harness/$h.json $W/verdicts/inv-$r.json $W/runs/$r.json --cache $W/verdicts --threads 8 > $W/logs/j-$r.log 2>&1
    note "JUGE $r rc=$? $(tail -1 $W/logs/j-$r.log)"
  done
done
python3 j.py $T/judge_validate_v3.py run controls.json $W/verdicts/validate-post.json > $W/logs/validate-post.log 2>&1; note "VALIDATION après rc=$? $(tail -1 $W/logs/validate-post.log)"
kill $SP; systemctl start ollama; note "ollama relancé, FIN"
