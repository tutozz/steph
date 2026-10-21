#!/bin/bash
# R3-T2 partie 1 : mix R1 (i1) recomposé sur le corpus réétiqueté X4 (data/final-x4), sur la machine qui porte le corpus.
# Chaîne R1 reproduite à l'octet sur data/final (md5 de train.fixed, mix-fixed-cap250, k3/mix et mix-i1 égaux) ;
# seules les entrées changent : fichiers X4 à la place de ceux de final/, sans les listes de rejets du juge 9B
# (consigne du README de final-x4) ; start, qa_train, summary_residual et mix-extra (questions, fonctionnalités EN) inchangés.
set -eu
W=/root/steph-ft/loop/r3t2p1; R=$W/repo; F=$R/bench/matrix/finetune; D=/root/steph-ft/data
cd $D
mkdir -p $W/x4 $W/logs
python3 - "$W/x4/fr.jsonl" <<'PY'
import sys
with open(sys.argv[1], "w") as out:
    for s in ["macos", "linux-low", "linux-dev", "snapshot-linux-dev", "snapshot-linux-low"]:
        out.writelines(open(f"final-x4/{s}.jsonl"))
PY
python3 $F/fix_labels.py $W/x4/fr.jsonl $W/x4/fr.fixed.jsonl
python3 $F/compose_train.py $W/x4/fr.fixed.jsonl $W/x4/fr-mix --cap 250 --bench $R/bench/matrix/cases.json
PYTHONPATH=$R/src python3 $F/compose_k3.py --fr-mix $W/x4/fr-mix --fr-raw corpus/*.jsonl snapshot-1/clean/*.jsonl \
  --en final-x4/macos.en.jsonl final-x4/linux-low.en.jsonl --en-raw corpus/*.en.jsonl \
  --feature detail=final-x4/detail.jsonl --feature start=final/start.jsonl --feature progress=final-x4/progress.jsonl \
  --feature flux=final-x4/flux.jsonl --feature summary_residual=final/summary_residual.jsonl --feature-raw corpus/features-*.jsonl \
  --qa final/qa_train.jsonl --bench $R/bench/matrix/cases.json --speak-bench $R/benchmark/data/v1 --max-chars 587 \
  --out $W/x4/k3mix > $W/logs/x4-k3mix.json
python3 $F/compose_r1.py --base $W/x4/k3mix --extra /root/steph-ft/r1/mix-extra --repeat en_summary=2 --keep detail=0.5 \
  --out $W/mix-x4 > $W/logs/mix-x4.json
