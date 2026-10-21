#!/bin/bash
# bench_all.sh : banc steph (cases_ft, 3 graines, rp 1.1) puis TermSpeak dev FR (temp 0.2, 3 graines), GPU Vulkan
V=/mnt/backup-hdd/stephbench-tmp/vocab; B=/root/stephbench-matrix/bin/vulkan/llama-b11205
cd $V/bench
for M in full-Q8_0 v32768-Q8_0 v20000-Q8_0 full-Q4_K_M v32768-Q4_K_M v20000-Q4_K_M; do
  ALL=""
  for sd in 42 7 123; do
    nice -n 19 python3 bench_run.py --server $B/llama-server --model $V/gguf/$M.gguf --label vocab-$M-s$sd --ngl 99 --port 8913 --ctx 4096 \
      --cases cases_ft.json --payload "{\"repeat_penalty\": 1.1, \"seed\": $sd}" --out $V/out/bench-$M-s$sd.json >> $V/out/bench.log 2>&1
    ALL="$ALL $V/out/bench-$M-s$sd.json"
  done
  echo "SCORE $M $(python3 score_opt.py $ALL --holdout)" >> $V/out/scores.txt
  R=$V/ts/$M; mkdir -p $R
  nice -n 19 $B/llama-server -m $V/gguf/$M.gguf --host 127.0.0.1 --port 8914 -c 4096 -ngl 99 --no-webui --jinja --parallel 1 > $R/server.log 2>&1 &
  SP=$!
  for i in $(seq 60); do curl -sf http://127.0.0.1:8914/health >/dev/null && break; sleep 1; done
  for sd in 42 7 123; do
    nice -n 19 python3 $V/termspeak/run.py --base-url http://127.0.0.1:8914/v1 --model steph --label ts-$M-s$sd --lang fr --split dev \
      --data $V/termspeak/data/v1 --out $R --temperature 0.2 --extra-body "{\"seed\": $sd, \"repeat_penalty\": 1.1}" --quiet >> $R/run.log 2>&1
  done
  kill $SP; wait $SP 2>/dev/null
  python3 -c "
import json,glob
s=[json.load(open(f))['summary']['score'] for f in sorted(glob.glob('$R/*.json'))]
print('TS', '$M', round(sum(s)/len(s),1), s)" >> $V/out/scores.txt
done
echo BENCH_ALL_DONE >> $V/out/scores.txt
