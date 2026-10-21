#!/bin/bash
# eval_t2.sh <gguf> <label> : même harnais que T1/K3 (bench_run.py md5 d08275ef, 36 cas granite200 TRAIN_SYSTEM, maxc 0,
# graines 7/42/123) puis Steph Speak Bench protocole steph, dev et test ; A1000 Vulkan1 ; ports propres à T2.
set -u
G=$1; L=$2
W=/root/steph-ft/loop/t2; E=$W/eval; R=$W/repo; B=/root/steph-ft/llama/vulkan; F=$R/bench/matrix/finetune
export LD_LIBRARY_PATH=$B
mkdir -p $E/bench $E/speak/$L $W/logs
cd $R/bench/matrix
for sd in 7 42 123; do
  OUT=$E/bench/$L-b$sd.json
  [ -f $OUT ] || python3 bench_run.py --server $B/llama-server --model $G --label $L-b$sd \
    --cases $R/bench/matrix/cases_compact_granite200_train.json --maxc 0 --port 8962 --ngl 99 --device Vulkan1 --payload "{\"seed\": $sd}" \
    --out $OUT >> $W/logs/eval-$L-bench.log 2>&1
done
S=$E/speak/$L
$B/llama-server -m $G --host 127.0.0.1 --port 8896 -c 4096 -ngl 99 --device Vulkan1 --no-webui --jinja --parallel 1 > $W/logs/eval-$L-server.log 2>&1 < /dev/null &
SP=$!
for i in $(seq 60); do python3 -c "import urllib.request;urllib.request.urlopen(\"http://127.0.0.1:8896/health\")" 2>/dev/null && break; sleep 1; done
run() {
  ls $S/*_$1_$2_$3.json >/dev/null 2>&1 && return 0
  python3 $R/benchmark/run.py --base-url http://127.0.0.1:8896/v1 --model steph --label $1 --out $S --quiet \
    --hardware "RTX A1000 Vulkan" --notes "X1 T2, Q4_K_M" --lang $2 --split $3 ${4:+--system-prompt-file $4} >> $W/logs/eval-$L-speak.log 2>&1
}
run $L-steph fr dev $F/train_system_prompt.txt
run $L-steph en dev $F/train_system_prompt.en.txt
run $L-steph fr test $F/train_system_prompt.txt
run $L-steph en test $F/train_system_prompt.en.txt
kill $SP
echo "$(date +%H:%M) EVAL $L" >> $W/run.done
