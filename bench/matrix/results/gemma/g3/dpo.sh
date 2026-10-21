#!/bin/bash
# G3 DPO sur la machine du corpus (3080). dpo.sh sample <gguf> | judge | build | train <graine> <adaptateurs SFT...>
# Rien ne quitte la machine : entrées, sorties, verdicts et paires restent sous $W/dpo.
set -u
W=/root/steph-ft/g3; D=$W/dpo; R=$W/repo; FG=$R/bench/matrix/finetune/gemma; T4=$R/bench/matrix/finetune/loop/r3t4
C=/root/steph-ft/loop/r3t4/code; B=/root/steph-ft/llama.cpp/build/bin; PY=/root/steph-ft/venv/bin/python
QWEN=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf; export JUDGE_PORT=8987 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd $D; mkdir -p logs judge/cache
note() { echo "$(date +%H:%M) $*" >> $D/run.done; }
vram() { while :; do f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); [ "$f" -ge $1 ] && return 0; sleep 30; done; }
case ${1:-} in
  sample)
    vram 5000
    for p in 8991 8992; do $B/llama-server -m $2 --host 127.0.0.1 --port $p -c 8192 -ngl 99 --parallel 2 --no-webui --jinja --reasoning-budget 0 > logs/gen-$p.log 2>&1 < /dev/null & echo $! >> logs/gen.pids; done
    for i in $(seq 90); do curl -sf http://127.0.0.1:8992/health >/dev/null && curl -sf http://127.0.0.1:8991/health >/dev/null && break; sleep 2; done
    PYTHONPATH=$R/src python3 $T4/onpolicy_sample.py sample --selected selected.jsonl --ports 8991,8992 --n 4 --workers 4 --out samples.jsonl > logs/sample.log 2>&1
    note "SAMPLE rc=$? $(tail -1 logs/sample.log)"
    kill $(cat logs/gen.pids); rm logs/gen.pids
    PYTHONPATH=$R/src python3 $T4/onpolicy_sample.py stats --selected selected.jsonl --samples samples.jsonl > logs/stats.json 2>&1 ;;
  judge)
    vram 6400
    $B/llama-server -m $QWEN --host 127.0.0.1 --port $JUDGE_PORT -c 16384 -ngl 99 --parallel 4 --no-webui --jinja --reasoning-budget 0 > logs/qwen.log 2>&1 < /dev/null &
    QP=$!
    for i in $(seq 120); do curl -sf http://127.0.0.1:$JUDGE_PORT/health >/dev/null && break; sleep 2; done
    export PYTHONPATH=$C/judge:$C:$T4
    python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/validate-pre.json > logs/validate-pre.log 2>&1; note "VALIDATION avant rc=$?"
    for P in A B; do
      python3 $C/j.py $T4/mask_pairs.py judge --pass $P --selected selected.jsonl --samples samples.jsonl --cache judge/cache --threads 8 --max-missing 5 > logs/judge-$P.log 2>&1
      note "JUGE $P rc=$? $(tail -1 logs/judge-$P.log)"
    done
    python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/validate-post.json > logs/validate-post.log 2>&1; note "VALIDATION après rc=$?"
    kill $QP ;;
  build)
    PYTHONPATH=$R/src python3 $FG/g3_pairs.py build --selected selected.jsonl --samples samples.jsonl --cache judge/cache --out pairs > logs/pairs.log 2>&1
    note "PAIRES rc=$? $(tail -1 logs/pairs.log)" ;;
  train)
    S=$2; shift 2; vram 9000
    cd $FG && PYTHONPATH=$R/src nice -n 19 $PY train_dpo_gemma.py --model /dev/shm/g3-qat --sft-adapters "$@" --pairs $D/pairs/pairs-train.jsonl \
      --val-pairs $D/pairs/pairs-val.jsonl --val $W/mix-x4r1/val.jsonl --out $D/dpo-s$S --generic-prompt --seed $S \
      --lr 1e-5 --beta 0.1 --sft-weight 1 --epochs 3 --batch 16 --micro 2 --maxlen 2048 > $D/logs/train-s$S.log 2>&1
    note "DPO s$S rc=$?" ;;
esac
