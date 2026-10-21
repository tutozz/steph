#!/bin/bash
# G3 : mix-x4r1 de R3-T3 recomposé sur la machine 3080 depuis son propre data/final-x4 (corpus jamais déplacé) ; sha256 attendu 89d793c8 / f629d3b5.
set -eu
W=/root/steph-ft/g3; R=$W/repo; F=$R/bench/matrix/finetune; D=/root/steph-ft/data
X=/dev/shm/g3-x4r1; mkdir -p $X/empty; : > $X/empty/train.jsonl; : > $X/empty/val.jsonl
cd $D
cat final-x4/macos.jsonl final-x4/linux-low.jsonl final-x4/linux-dev.jsonl final-x4/snapshot-linux-dev.jsonl final-x4/snapshot-linux-low.jsonl > $X/fr.jsonl
nice -n 19 python3 $F/fix_labels.py $X/fr.jsonl $X/fr.fixed.jsonl
nice -n 19 python3 $F/compose_train.py $X/fr.fixed.jsonl $X/fr-mix --cap 250 --bench $R/bench/matrix/cases.json
PYTHONPATH=$R/src nice -n 19 python3 $F/compose_k3.py --fr-mix $X/fr-mix --fr-raw corpus/*.jsonl snapshot-1/clean/*.jsonl \
  --en final-x4/macos.en.jsonl final-x4/linux-low.en.jsonl --en-raw corpus/*.en.jsonl \
  --feature detail=final-x4/detail.jsonl --feature start=final/start.jsonl --feature progress=final-x4/progress.jsonl \
  --feature flux=final-x4/flux.jsonl --feature summary_residual=final/summary_residual.jsonl --feature-raw corpus/features-*.jsonl \
  --qa final/qa_train.jsonl --bench $R/bench/matrix/cases.json --speak-bench $R/benchmark/data/v1 --max-chars 587 \
  --out $X/k3mix > $W/logs/k3mix.json
nice -n 19 python3 $F/compose_r1.py --base $X/k3mix --extra $X/empty --repeat en_summary=2 --keep detail=0.5 --out $W/mix-x4r1 > $W/logs/mix-x4r1.json
rm -rf $X
sha256sum $W/mix-x4r1/*.jsonl
