#!/bin/bash
# G5d, DEV rapide : banc v3 aligné L5 (dev.json, harnais affiné) de G5d, mêmes binaire (CUDA 9588757) et commande que
# eval_3080.sh de G5c ; langue sous prompt EN contre les runs DEV de G5c et a-sft de G5c (g5_eval.py, sans juge).
# Graine 7 d'abord (décision rapide), puis 42 et 123 (même coût, quelques minutes). g5_eval.py demande numpy :
# python du venv (le python3 de l'hôte n'en a pas, échec du 2026-10-01).
set -u
K=/root/steph-ft/g5d; R=$K/repo; B=/root/steph-ft/llama.cpp/build/bin; C=/root/steph-ft/g5c; G=$K/gguf/g5d-a-sft-Q4_K_M.gguf
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
cd $K; mkdir -p runs eval
for sd in 7 42 123; do
  O=$K/runs/g5d-dev-b$sd.json
  [ -f $O ] && continue
  until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge 3000 ]; do sleep 60; done
  nice -n 5 python3 $R/bench/matrix/bench_run.py --server $B/llama-server --model $G --label g5d-g5d-v3dev-b$sd \
    --cases $R/bench/matrix/v3/harness/dev.json --maxc 0 --port 898${sd: -1} --ngl 99 --abort-ttft 120 \
    --payload "{\"seed\": $sd}" --out $O >> $K/logs/bench-dev.log 2>&1
  note "BANC g5d dev b$sd rc=$?"
done
cmp() {  # dossier graines : runs G5d, G5c, a-sft liés, g5_eval.py sans verdicts ni formulation
  mkdir -p $K/$1 $K/empty
  for sd in $2; do
    ln -sfn $K/runs/g5d-dev-b$sd.json $K/$1/; for m in g5c a-sft; do ln -sfn $C/runs/$m-dev-b$sd.json $K/$1/; done
  done
  PYTHONPATH=$R/bench/matrix/v3/tools:$R/bench/matrix/results/finetune/loop/round-3/r3t2p3:$R/bench/matrix/finetune \
    /root/steph-ft/venv/bin/python $R/bench/matrix/results/g5/g5_eval.py dev $K/$1 $K/empty $K/empty $R/bench/matrix/v3/harness $K/eval/g5d-eval-$1.json \
    > $K/logs/eval-$1.out 2> $K/logs/eval-$1.err
  note "EVAL $1 rc=$? $(python3 -c "import json,sys; r=json.load(open(sys.argv[1])); print({m: (v['wrong_lang_pct']['@en'], v['wrong_lang_en_fr_output_pct'], v['quality']) for m, v in r['models'].items()})" $K/eval/g5d-eval-$1.json)"
}
cmp dev-b7 7
cmp dev-3 "7 42 123"
note "FIN DEV"
