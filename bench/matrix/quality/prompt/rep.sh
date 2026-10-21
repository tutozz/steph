#!/bin/bash
# Répétitions d'une variante (température 0,2 : bruit de ±7 points) : [K=3] rep.sh <modèle> <variante> "<desc>" [args gen.py]
# Choix sur la moyenne tune ; le contrôle est affiché pour information seulement.
M=$1; V=$2; D=$3; shift 3
J=bench/matrix/results/quality/prompt/journal.tsv
for r in $(seq 1 ${K:-3}); do
  N=$(( $(wc -l < $J) + 1 ))
  REP=$r ./run.sh $N $M $V "$D" "$@" | cut -d" " -f4,5
done | tr '\n=' '  ' | awk -v v="$M $V" '{t=0;h=0;n=0; for(i=1;i<=NF;i+=4){t+=$(i+1); h+=$(i+3); n++} printf "%s tune=%.1f holdout=%.1f (n=%d)\n", v, t/n, h/n, n}'
