#!/bin/bash
# G3b sur l'hôte de la 3060 (corpus sur place, jamais déplacé) : correctif de langue (enseignant et juge A7 Qwen3.5 9B),
# mix de G3 (chaîne R3-T3) sur data/final-x4-l5 plus les lignes du correctif, contamination, puis SFT graine 42 recette G3.
set -u
T=/mnt/backup-hdd/stephbench-tmp; G=$T/gemma/g3b; R=$G/repo; F=$R/bench/matrix/finetune; D=$T/ft/data; W=$G/work
C=$T/loop/r3t4/code; B=/root/stephbench-matrix/bin/vulkan/llama-b11205; QWEN=$T/models/Qwen3.5-9B-Q4_K_M.gguf; P=8990
export LD_LIBRARY_PATH=$B
note() { echo "$(date +%H:%M) $*" >> $G/run.done; }
cd $W
if [ ! -f langfix.jsonl ]; then
  while [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]; do sleep 120; done
  nice -n 19 $B/llama-server -m $QWEN --host 127.0.0.1 --port $P -c 16384 -ngl 99 --parallel 4 --no-webui --jinja --reasoning-budget 0 > $G/logs/qwen.log 2>&1 < /dev/null &
  QP=$!
  for i in $(seq 120); do curl -sf http://127.0.0.1:$P/health >/dev/null && break; sleep 2; done
  note "juge et enseignant $(sha256sum $QWEN | cut -c1-16)"
  JUDGE_PORT=$P PYTHONPATH=$C/judge python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json validate-pre.json > $G/logs/validate-pre.log 2>&1; note "VALIDATION avant rc=$? $(tail -1 $G/logs/validate-pre.log)"
  PYTHONPATH=$R/src nice -n 19 python3 $F/gemma/g3b_langfix.py label --in subset.jsonl --port $P --parallel 4 --out labeled.jsonl > $G/logs/label.log 2>&1; note "ÉTIQUETTES rc=$? $(tail -1 $G/logs/label.log)"
  PYTHONPATH=$R/src python3 $F/gemma/g3b_langfix.py rows --labeled labeled.jsonl --out cand.jsonl > $G/logs/rows.log 2>&1; note "LANGUE $(tail -1 $G/logs/rows.log)"
  mkdir -p judge
  JUDGE_PORT=$P PYTHONPATH=$C/judge nice -n 19 python3 $C/j.py $F/judge_corpus_2pass.py cand.jsonl langfix judge > $G/logs/judge.log 2>&1; note "JUGE rc=$? $(tail -1 $G/logs/judge.log)"
  JUDGE_PORT=$P PYTHONPATH=$C/judge python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json validate-post.json > $G/logs/validate-post.log 2>&1; note "VALIDATION après rc=$? $(tail -1 $G/logs/validate-post.log)"
  kill $QP; sleep 10
  PYTHONPATH=$R/src python3 $F/gemma/g3b_langfix.py keep --cand cand.jsonl --verdicts judge/verdicts-langfix.jsonl --n 300 --seed 42 --out langfix.jsonl > $G/logs/keep.log 2>&1; note "GARDÉES $(tail -1 $G/logs/keep.log)"
fi
if [ ! -f mix-x4r1-l5/train.jsonl ]; then
  X=$W/x4r1; mkdir -p $X/empty; : > $X/empty/train.jsonl; : > $X/empty/val.jsonl
  cd $D
  cat final-x4-l5/macos.jsonl final-x4-l5/linux-low.jsonl final-x4-l5/linux-dev.jsonl final-x4-l5/snapshot-linux-dev.jsonl \
    final-x4-l5/snapshot-linux-low.jsonl > $X/fr.jsonl
  nice -n 19 python3 $F/fix_labels.py $X/fr.jsonl $X/fr.fixed.jsonl
  nice -n 19 python3 $F/compose_train.py $X/fr.fixed.jsonl $X/fr-mix --cap 250 --bench $R/bench/matrix/cases.json
  PYTHONPATH=$R/src nice -n 19 python3 $F/compose_k3.py --fr-mix $X/fr-mix --fr-raw corpus/*.jsonl snapshot-1/clean/*.jsonl \
    --en final-x4-l5/macos.en.jsonl final-x4-l5/linux-low.en.jsonl --en-raw corpus/*.en.jsonl \
    --feature detail=final-x4-l5/detail.jsonl --feature start=final/start.jsonl --feature progress=final-x4-l5/progress.jsonl \
    --feature flux=final-x4-l5/flux.jsonl --feature summary_residual=final/summary_residual.jsonl --feature-raw corpus/features-*.jsonl \
    --qa final/qa_train.jsonl --bench $R/bench/matrix/cases.json --speak-bench $R/benchmark/data/v1 --max-chars 587 \
    --out $X/k3mix > $G/logs/k3mix.json
  nice -n 19 python3 $F/compose_r1.py --base $X/k3mix --extra $X/empty --repeat en_summary=2 --keep detail=0.5 \
    --out $W/mix-x4r1-l5 > $G/logs/mix-x4r1-l5.json
  rm -rf $X
fi
if [ ! -f mix/train.jsonl ]; then
  # contamination à l'échelle de la ligne : toute ligne qui fait rejeter un cas du banc v3 (empreintes au HEAD, entrées L5) sort
  cd $W && mkdir -p clean mix
  for f in langfix mix-x4r1-l5/train mix-x4r1-l5/val; do
    nice -n 19 python3 $R/bench/matrix/v3/tools/leak_check.py drop v3prints-head.json $f.jsonl clean/$(echo $f | tr / -).jsonl > $G/logs/drop-$(echo $f | tr / -).log; note "SANS FUITE $f $(cat $G/logs/drop-$(echo $f | tr / -).log)"
  done
  # correctif répété deux fois, comme les résumés anglais du mix (compose_r1 --repeat en_summary=2)
  cat clean/mix-x4r1-l5-train.jsonl clean/langfix.jsonl clean/langfix.jsonl > mix/train.jsonl && cp clean/mix-x4r1-l5-val.jsonl mix/val.jsonl
  nice -n 19 python3 $R/bench/matrix/v3/tools/leak_check.py scan v3prints-head.json leak-mix.json mix/train.jsonl mix/val.jsonl > $G/logs/leak.log 2>&1; note "FUITE rc=$? $(tail -1 $G/logs/leak.log)"
  sha256sum mix-x4r1-l5/*.jsonl mix/*.jsonl langfix.jsonl | sed "s|  | |" > $G/logs/mix-sha.txt; note "MIX $(wc -l < mix/train.jsonl) / $(wc -l < mix/val.jsonl)"
fi
cd $W
if [ ! -f $G/sft-s42/adapter/adapter_model.safetensors ]; then
  grep -q '"rejected": \[\]' $G/logs/leak.log || { note "ARRÊT : cas du banc dans le mix"; exit 1; }
  while [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]; do sleep 5; done
  note "SFT départ"
  cd $F/gemma && PYTHONPATH=$R/src nice -n 19 $T/ft/venv/bin/python train_sft_gemma.py --model $T/gemma/qat \
    --train $W/mix/train.jsonl --val $W/mix/val.jsonl --out $G/sft-s42 --generic-prompt \
    --batch 16 --micro 4 --maxlen 2048 --lr 1e-4 --epochs 2 --evals-per-epoch 4 --patience 3 --seed 42 > $G/logs/sft-s42.log 2>&1
  note "SFT rc=$? $(tail -1 $G/logs/sft-s42.log)"
fi
note "FIN"
