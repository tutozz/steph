#!/bin/bash
# R3-T3 : mix de l'enseignant sur l'hôte de la 3060, chaîne R1 de r3_t2_x4/build_mix.sh sur data/final-x4, sans mix-extra.
# mix-extra (questions FR/EN filtrées, fonctionnalités EN) n'existe que sur la 3080 et ne quitte pas sa machine :
# extra vide, puis même pondération que R1 (en_summary x2, detail 0,5). Contamination contrôlée contre v3 0db04fa.
set -eu
W=/mnt/backup-hdd/stephbench-tmp/loop/r3t3; R=$W/repo; F=$R/bench/matrix/finetune; D=/mnt/backup-hdd/stephbench-tmp/ft/data
X=$W/work/x4r1; mkdir -p $X/empty $W/logs
: > $X/empty/train.jsonl; : > $X/empty/val.jsonl
cd $D
cat final-x4/macos.jsonl final-x4/linux-low.jsonl final-x4/linux-dev.jsonl final-x4/snapshot-linux-dev.jsonl \
  final-x4/snapshot-linux-low.jsonl > $X/fr.jsonl
nice -n 19 python3 $F/fix_labels.py $X/fr.jsonl $X/fr.fixed.jsonl
nice -n 19 python3 $F/compose_train.py $X/fr.fixed.jsonl $X/fr-mix --cap 250 --bench $R/bench/matrix/cases.json
PYTHONPATH=$R/src nice -n 19 python3 $F/compose_k3.py --fr-mix $X/fr-mix --fr-raw corpus/*.jsonl snapshot-1/clean/*.jsonl \
  --en final-x4/macos.en.jsonl final-x4/linux-low.en.jsonl --en-raw corpus/*.en.jsonl \
  --feature detail=final-x4/detail.jsonl --feature start=final/start.jsonl --feature progress=final-x4/progress.jsonl \
  --feature flux=final-x4/flux.jsonl --feature summary_residual=final/summary_residual.jsonl --feature-raw corpus/features-*.jsonl \
  --qa final/qa_train.jsonl --bench $R/bench/matrix/cases.json --speak-bench $R/benchmark/data/v1 --max-chars 587 \
  --out $X/k3mix > $W/logs/x4r1-k3mix.json
nice -n 19 python3 $F/compose_r1.py --base $X/k3mix --extra $X/empty --repeat en_summary=2 --keep detail=0.5 \
  --out $W/work/mix-x4r1 > $W/logs/mix-x4r1.json
nice -n 19 python3 $R/bench/matrix/v3/tools/leak_check.py scan $W/work/v3prints-0db04fa.json $W/work/leak-mix-x4r1.json \
  $W/work/mix-x4r1/train.jsonl $W/work/mix-x4r1/val.jsonl > $W/logs/leak-x4r1.log
rm -rf $X
