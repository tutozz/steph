#!/bin/bash
# G3 DPO sur la machine 3060 (même corpus, même sélection que la 3080 : sha256 4d0b0f1b). dpo.sh sample <gguf> | judge | build | train <graine> <adaptateurs SFT...>
# Rien ne quitte la machine : entrées, sorties, verdicts et paires restent sous $W/dpo.
set -u
W=/mnt/backup-hdd/stephbench-tmp/gemma/g3; D=$W/dpo; R=$W/repo; FG=$R/bench/matrix/finetune/gemma; T4=$R/bench/matrix/finetune/loop/r3t4
C=/mnt/backup-hdd/stephbench-tmp/loop/r3t4/code; B=/root/stephbench-matrix/bin/vulkan/llama-b11205; PY=/mnt/backup-hdd/stephbench-tmp/ft/venv/bin/python
QWEN=/mnt/backup-hdd/stephbench-tmp/models/Qwen3.5-9B-Q4_K_M.gguf; export JUDGE_PORT=8987 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True LD_LIBRARY_PATH=$B
cd $D; mkdir -p logs judge/cache
note() { echo "$(date +%H:%M) $*" >> $D/run.done; }
free_gpu() { while :; do f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l); [ "$f" -ge $1 ] && [ "$n" -eq 0 ] && return 0; sleep 60; done; }
case ${1:-} in
  sample)
    free_gpu 9000
    for p in 8991 8992; do nice -n 19 $B/llama-server -m $2 --host 127.0.0.1 --port $p -c 8192 -ngl 99 --parallel 2 --no-webui --jinja --reasoning-budget 0 > logs/gen-$p.log 2>&1 < /dev/null & echo $! >> logs/gen.pids; done
    for i in $(seq 90); do curl -sf http://127.0.0.1:8992/health >/dev/null && curl -sf http://127.0.0.1:8991/health >/dev/null && break; sleep 2; done
    PYTHONPATH=$R/src python3 $T4/onpolicy_sample.py sample --selected selected.jsonl --ports 8991,8992 --n 4 --workers 4 --out samples.jsonl > logs/sample.log 2>&1
    note "SAMPLE rc=$? $(tail -1 logs/sample.log)"
    kill $(cat logs/gen.pids); rm logs/gen.pids; sleep 5
    PYTHONPATH=$R/src python3 $T4/onpolicy_sample.py stats --selected selected.jsonl --samples samples.jsonl > logs/stats.json 2>&1 ;;
  judge)
    free_gpu 9000
    nice -n 19 $B/llama-server -m $QWEN --host 127.0.0.1 --port $JUDGE_PORT -c 16384 -ngl 99 --parallel 4 --no-webui --jinja --reasoning-budget 0 > logs/qwen.log 2>&1 < /dev/null &
    QP=$!
    for i in $(seq 120); do curl -sf http://127.0.0.1:$JUDGE_PORT/health >/dev/null && break; sleep 2; done
    export PYTHONPATH=$C/judge:$C:$T4
    python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/validate-pre.json > logs/validate-pre.log 2>&1; note "VALIDATION avant rc=$? $(tail -1 logs/validate-pre.log)"
    for P in A B; do
      python3 $C/j.py $T4/mask_pairs.py judge --pass $P --selected selected.jsonl --samples samples.jsonl --cache judge/cache --threads 8 --max-missing 5 > logs/judge-$P.log 2>&1
      note "JUGE $P rc=$? $(tail -1 logs/judge-$P.log)"
    done
    python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/validate-post.json > logs/validate-post.log 2>&1; note "VALIDATION après rc=$? $(tail -1 logs/validate-post.log)"
    kill $QP; sleep 5 ;;
  build)
    PYTHONPATH=$R/src python3 $FG/g3_pairs.py build --selected selected.jsonl --samples samples.jsonl --cache judge/cache --out pairs > logs/pairs.log 2>&1
    note "PAIRES rc=$? $(tail -1 logs/pairs.log)" ;;
  train)
    S=$2; shift 2; free_gpu 10000
    cd $FG && PYTHONPATH=$R/src nice -n 19 $PY train_dpo_gemma.py --model /mnt/backup-hdd/stephbench-tmp/gemma/qat --sft-adapters "$@" --pairs $D/pairs/pairs-train.jsonl \
      --val-pairs $D/pairs/pairs-val.jsonl --val /mnt/backup-hdd/stephbench-tmp/loop/r3t3/work/mix-x4r1/val.jsonl --out $D/dpo-s$S --generic-prompt --seed $S \
      --lr 1e-5 --beta 0.1 --sft-weight 1 --epochs 3 --batch 16 --micro 2 --maxlen 2048 > $D/logs/train-s$S.log 2>&1
    note "DPO s$S rc=$?" ;;
esac
