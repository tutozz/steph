#!/bin/bash
# G4 : second juge A7 sur la 3080 (même Qwen3.5 9B Q4_K_M 03b74727, même judge_lib, contrôles avant et après),
#   graines supplémentaires dans l'ordre inverse de la 3060 pour finir plus tôt. judge-3080.sh <run>...
set -u
W=/root/steph-ft/g4; J=/root/steph-ft/g3/eval/judge; P=8997
M=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf; SRV=/root/steph-ft/llama.cpp/build/bin/llama-server
T=/root/steph-ft/g3/eval/repo/bench/matrix/v3/tools
note() { echo "$(date +%T) $*" >> $W/logs/judge-3080.done; }
cd $J; mkdir -p $W/verdicts
until [ "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l)" -eq 0 ] && [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge 8000 ]; do sleep 60; done
systemctl stop ollama; note "ollama arrêté"
sha256sum $M | cut -c1-16 >> $W/logs/judge-3080.done
nice -n 5 $SRV -m $M --host 127.0.0.1 --port $P -c 16384 --parallel 4 -ngl 99 --jinja --no-webui --reasoning-budget 0 > $W/logs/qwen-3080.log 2>&1 < /dev/null &
SP=$!
for i in $(seq 180); do curl -sf http://127.0.0.1:$P/health > /dev/null && break; sleep 2; done
export JUDGE_PORT=$P PYTHONPATH=$J/jl:$T
python3 j.py $T/judge_validate_v3.py run controls.json $W/verdicts/validate-3080-pre.json > $W/logs/validate-3080-pre.log 2>&1; note "VALIDATION avant rc=$? $(tail -1 $W/logs/validate-3080-pre.log)"
for m in "$@"; do
  python3 judge_x3.py /root/steph-ft/g3/eval/harness/test.generic.json $W/verdicts/inv-$m.json $W/runs/$m.json --cache cache --threads 8 > $W/logs/j3080-$m.log 2>&1
  note "JUGE $m rc=$? $(tail -1 $W/logs/j3080-$m.log)"
done
python3 j.py $T/judge_validate_v3.py run controls.json $W/verdicts/validate-3080-post.json > $W/logs/validate-3080-post.log 2>&1; note "VALIDATION après rc=$? $(tail -1 $W/logs/validate-3080-post.log)"
kill $SP; systemctl start ollama; note "ollama relancé, FIN"
