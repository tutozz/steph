#!/bin/bash
# run_eval_k3.sh <gguf> <label> : harnais P17 (banc 36 cas granite200 TRAIN_SYSTEM, 3 graines) puis Steph Speak Bench
# (protocole steph : TRAIN_SYSTEM en FR, TRAIN_SYSTEM_EN en EN comme le profil affiné de production, dev et test ;
# protocole standard, test FR et EN, comme C3). Le juge (juge_bench.py, speak_unresolved.py) tourne à part, serveur Qwen sur 8931.
set -u
G=$1; L=$2
K=${K3:-/root/steph-ft/k3}; E=$K/eval; R=$K/repo; B=/root/steph-ft/llama.cpp/build/bin
mkdir -p $E/bench $E/speak/$L $K/logs
cd /root/steph-ft/ft/bench
for sd in 7 42 123; do
  OUT=$E/bench/$L-b$sd.json
  [ -f $OUT ] || python3 bench_run.py --server $B/llama-server --model $G --label $L-b$sd \
    --cases $R/bench/matrix/cases_compact_granite200_train.json --maxc 0 --port 8960 --ngl 99 --payload "{\"seed\": $sd}" \
    --out $OUT >> $K/logs/eval-$L-bench.log 2>&1
done
S=$E/speak/$L
F=$R/bench/matrix/finetune
$B/llama-server -m $G --host 127.0.0.1 --port 8894 -c 4096 -ngl 99 --no-webui --jinja --parallel 1 > $K/logs/eval-$L-server.log 2>&1 < /dev/null &
SP=$!
for i in $(seq 60); do curl -sf http://127.0.0.1:8894/health >/dev/null && break; sleep 1; done
run() {  # étiquette, langue, split, [fichier de prompt système]
  ls $S/*_$1_$2_$3.json >/dev/null 2>&1 && return 0
  python3 $R/benchmark/run.py --base-url http://127.0.0.1:8894/v1 --model steph --label $1 --out $S --quiet \
    --hardware "RTX 3080 CUDA" --notes "K3, Q4_K_M" --lang $2 --split $3 ${4:+--system-prompt-file $4} >> $K/logs/eval-$L-speak.log 2>&1
}
run $L-steph fr dev $F/train_system_prompt.txt
run $L-steph en dev $F/train_system_prompt.en.txt
run $L-steph fr test $F/train_system_prompt.txt
run $L-steph en test $F/train_system_prompt.en.txt
run $L fr test
run $L en test
kill $SP
echo "EVAL $L" >> $K/run.done
