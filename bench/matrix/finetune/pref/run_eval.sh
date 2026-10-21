#!/bin/bash
# run_eval.sh <gguf> <label> : banc 36 cas (graines 42, 7, 123) puis TermSpeak dev FR (3 graines), mêmes réglages que soup_run.sh et opt/ts.sh
set -u
G=$1; L=$2; P=/root/steph-ft/pref; B=/root/steph-ft/llama.cpp/build/bin; O=/root/steph-ft/opt
mkdir -p $P/bench $P/ts/$L $P/logs
cd /root/steph-ft/ft/bench
for sd in 42 7 123; do
  OUT=$P/bench/$L-b$sd.json
  [ -f $OUT ] || python3 bench_run.py --server $B/llama-server --model $G --label $L-b$sd --ngl 99 --port 8893 --ctx 4096 --parallel 1 \
    --cases cases_ft.json --payload "{\"repeat_penalty\": 1.1, \"seed\": $sd}" --out $OUT >> $P/logs/$L-bench.log 2>&1
done
R=$P/ts/$L
if ! ls $R/*.json >/dev/null 2>&1; then
  $B/llama-server -m $G --host 127.0.0.1 --port 8894 -c 4096 -ngl 99 --no-webui --jinja --parallel 1 > $R/server.log 2>&1 &
  SP=$!
  for i in $(seq 60); do curl -sf http://127.0.0.1:8894/health >/dev/null && break; sleep 1; done
  for sd in 42 7 123; do
    python3 $O/termspeak/run.py --base-url http://127.0.0.1:8894/v1 --model steph --label ts-$L-s$sd --lang fr --split dev \
      --data $O/termspeak/data/v1 --out $R --temperature 0.2 --extra-body "{\"seed\": $sd, \"repeat_penalty\": 1.1}" \
      --notes "prompt système court d'entraînement, Q4_K_M" --quiet >> $R/run.log 2>&1
  done
  kill $SP
fi
python3 -c "
import json,glob
s=[json.load(open(f))['summary']['score'] for f in sorted(glob.glob('$R/*.json'))]
print('TS', '$L', round(sum(s)/len(s),1), s)"
