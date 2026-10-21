#!/bin/bash
# G5 : Steph Speak Bench, protocole steph (TRAIN_SYSTEM en FR, TRAIN_SYSTEM_EN en EN, comme run_eval_k3.sh), split test,
# température 0, sur l'hôte de la 3080, un modèle à la fois ; --cache-ram 0 (Granite H hybride).
#   speak.sh <label> <gguf>
set -u
L=$1; G=$2
K=/root/steph-ft/g5; R=$K/repo; F=$R/bench/matrix/finetune; B=/root/steph-ft/llama.cpp/build/bin; S=$K/speak/$L; P=8894
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
mkdir -p $S
nice -n 5 $B/llama-server -m $G --host 127.0.0.1 --port $P -c 4096 -ngl 99 --no-webui --jinja --parallel 1 --cache-ram 0 \
  > $K/logs/speak-$L-server.log 2>&1 < /dev/null &
SP=$!
for i in $(seq 60); do curl -sf http://127.0.0.1:$P/health >/dev/null && break; sleep 1; done
for spec in fr:train_system_prompt.txt en:train_system_prompt.en.txt; do
  lang=${spec%%:*}
  ls $S/*_$L-steph_${lang}_test.json >/dev/null 2>&1 && continue
  python3 $R/benchmark/run.py --base-url http://127.0.0.1:$P/v1 --model steph --label $L-steph --out $S --quiet \
    --hardware "RTX 3080 CUDA" --notes "G5, Q4_K_M" --lang $lang --split test --system-prompt-file $F/${spec#*:} \
    >> $K/logs/speak-$L.log 2>&1
  note "SPEAK $L $lang rc=$?"
done
kill $SP
