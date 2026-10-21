#!/bin/bash
# X3 : file du juge A7 (2 passes) ; client sur le Mac, serveur 9B sur une carte du labo (tunnel local).
# judge_x3.py : réponses reaches_model du split test seulement, cache des réponses identiques ;
# contexte jugé = harnais que le modèle a lu (affiné ou générique). Reprenable.
# usage : judgeq.sh <port local du juge> <racine du banc figé> <graine> <nom:profil> ...
R=$(cd "$(dirname "$0")/.." && pwd); port=$1; head=$2; sd=$3; shift 3
mkdir -p $R/judge/verdicts $R/judge/logs
cd $head
for spec in "$@"; do
  m=${spec%%:*}; prof=${spec#*:}
  H=$head/bench/matrix/v3/harness/test.json; [ "$prof" = gen ] && H=$head/bench/matrix/v3/harness/test.generic.json
  RUN=$R/runs/$m-test-b$sd.json
  until [ -f "$RUN" ]; do sleep 120; $R/sync.sh; done
  JUDGE_PORT=$port PYTHONPATH=$R/judge/jl:$head/bench/matrix/v3/tools python3 $R/judge_x3.py \
    $H $R/judge/verdicts/inv-$m-test-b$sd.json $RUN --cache $R/judge/verdicts --threads 4 >> $R/judge/logs/$m-test-b$sd.log 2>&1
  echo "$(date +%T) $m test b$sd rc=$?" >> $R/judge/queue.log
done
echo QDONE >> $R/judge/queue.log
