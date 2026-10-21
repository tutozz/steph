#!/bin/bash
# screen_eval.sh <nom> <adaptateur> : P17 + un adaptateur SFT (une graine) -> GGUF -> banc 36 cas, 3 graines -> score v2.
set -u
N=$1; A=$2
R=/root/steph-ft/r1; F=$R/repo/bench/matrix/finetune; B=/root/steph-ft/llama.cpp/build/bin; PY=/root/steph-ft/venv/bin/python
G=$R/gguf/screen-$N-Q4_K_M.gguf; E=$R/eval-screen
mkdir -p $E $R/gguf
if [ ! -f $G ]; then
  $PY $F/pref/merge_pref.py --base $R/base-p17 --out /tmp/screen-$N --sft $A > $R/logs/screen-$N-merge.log 2>&1 || exit 1
  cp $R/base-p17/config.json /tmp/screen-$N/config.json
  $PY /root/steph-ft/llama.cpp/convert_hf_to_gguf.py /tmp/screen-$N --outfile /tmp/screen-$N-f16.gguf --outtype f16 > $R/logs/screen-$N-conv.log 2>&1 || exit 1
  $B/llama-quantize /tmp/screen-$N-f16.gguf $G Q4_K_M > $R/logs/screen-$N-q.log 2>&1 || exit 1
  rm -rf /tmp/screen-$N /tmp/screen-$N-f16.gguf
fi
cd /root/steph-ft/ft/bench
for sd in 7 42 123; do
  [ -f $E/$N-b$sd.json ] || python3 bench_run.py --server $B/llama-server --model $G --label $N-b$sd \
    --cases $R/repo/bench/matrix/cases_compact_granite200_train.json --maxc 0 --port 8961 --ngl 99 --payload "{\"seed\": $sd}" \
    --out $E/$N-b$sd.json >> $R/logs/screen-$N-bench.log 2>&1
done
PYTHONPATH=$R/repo/src python3 $F/pref/score_compact.py $R/repo/bench/matrix/cases_compact_granite200_train.json $E/$N-b7.json $E/$N-b42.json $E/$N-b123.json > $E/score-$N.json
echo "$(date +%H:%M) SCREEN $N $(python3 -c "import json;d=json.load(open('$E/score-$N.json'))['v2'];print(d['total'],d['holdout'],d['qa'])")" >> $R/run.done
