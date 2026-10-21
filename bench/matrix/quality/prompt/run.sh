#!/bin/bash
# Un essai de l'axe A : run.sh <n° essai> <modèle> <variante> "<description>" [args de gen.py...]
set -u
N=$1; MODEL=$2; VAR=$3; DESC=$4; shift 4
HERE=bench/matrix
Q=$HERE/quality/prompt
R=$HERE/results/quality/prompt
M=/tmp/models
case $MODEL in
  qwen35) GGUF=$M/Qwen3.5-0.8B-Q4_K_M.gguf ;;
  lfm25) GGUF=$M/LFM2.5-350M-Q4_K_M.gguf ;;
  granite) GGUF=$M/granite-4.0-h-350m-Q4_K_M.gguf ;;
  gemma3) GGUF=$M/gemma-3-270m-it-Q8_0.gguf ;;
  luth) GGUF=$M/LFM2-350M-Q4_K_M.gguf ;;
esac
mkdir -p $R
CASES=cases_$VAR.json
[ -f $Q/$CASES ] || python3 $Q/gen.py --out $CASES "$@" >/dev/null
LABEL=q-prompt-$MODEL-$VAR${REP:+-r$REP}
python3 $HERE/bench_run.py --server /opt/homebrew/bin/llama-server --model $GGUF --label $LABEL \
  --ngl 99 --port 8860 --maxc 800 --cases $Q/$CASES --out $R/$LABEL.json >/dev/null 2>&1
S=$(python3 $HERE/score.py $R/$LABEL.json)
T=$(echo "$S" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['tune'],d['holdout'])")
set -- $T
NOTE=$CASES; python3 -c "import sys; sys.exit(0 if float('$1')-float('$2')>20 else 1)" && NOTE="$CASES ; écart tune-contrôle > 20"
printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$N" "$MODEL" "$VAR${REP:+-r$REP} ($DESC)" "$1" "$2" "$NOTE" >> $R/journal.tsv
echo "$N $MODEL $VAR tune=$1 holdout=$2"
