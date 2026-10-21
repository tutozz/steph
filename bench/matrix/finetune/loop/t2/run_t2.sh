#!/bin/bash
# T2 sur le nœud A1000 (mix K3 exact) : influence des couches, découpe, soin SFT + KD, GGUF Q4_K_M ; intermédiaires supprimés après GGUF
set -u
T=/root/steph-ft/loop/t2; PY=/root/steph-ft/venv/bin/python; L=$T/repo/loop; LL=/root/steph-ft/llama
M=/root/steph-ft/k3/mix
export HF_HOME=/root/steph-ft/hf-cache HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd $T; mkdir -p gguf
note() { echo "$(date +%H:%M) $*" >> $T/run.done; }
[ -f scores.json ] || { nice -n 10 $PY $L/prune_granite.py score --model k3a-merged --data $M/train.jsonl --val $M/val.jsonl \
  --n 200 --drops 4 7 9 --out scores.json > logs/score.log 2>&1 || { note "SCORE KO"; exit 1; }; note "SCORE"; }
for k in ${KS:-7 9 4}; do
  [ -f gguf/t2-cut$k-Q4_K_M.gguf ] && continue
  drop=$(python3 -c "import json;d=json.load(open('scores.json'))['drops']['$k'];print(' '.join(map(str,d[d['chosen']]['drop'])))")
  [ -d cut$k ] || $PY $L/prune_granite.py cut --model k3a-merged --drop $drop --out cut$k > logs/cut$k.log 2>&1
  nice -n 10 $PY $L/heal_kd.py --student cut$k --teacher k3a-merged --train $M/train.jsonl --val $M/val.jsonl --out heal$k \
    --epochs 2 --alpha 0.5 --temp 2 --lr ${LR:-5e-5} --micro ${MICRO:-4} > logs/heal$k.log 2>&1 || { note "SOIN KO $k"; exit 1; }
  cp cut$k/config.json heal$k/merged/config.json
  nice -n 10 $PY $LL/llama.cpp-src/convert_hf_to_gguf.py heal$k/merged --outfile heal$k/f16.gguf --outtype f16 > logs/conv$k.log 2>&1 || { note "CONV KO $k"; exit 1; }
  LD_LIBRARY_PATH=$LL/cpu $LL/cpu/llama-quantize heal$k/f16.gguf gguf/t2-cut$k-Q4_K_M.gguf Q4_K_M > logs/q$k.log 2>&1 || { note "QUANT KO $k"; exit 1; }
  cp heal$k/train_log.json logs/heal$k-train_log.json
  rm -rf heal$k/merged heal$k/f16.gguf cut$k
  note "GGUF $k drop=[$drop] $(python3 -c "import json;d=json.load(open('logs/heal$k-train_log.json'));print('val', round(d['val_before'],4), '->', round(d['best_val'],4), 'ep', d['best_epoch'], d['train_s'], 's', d['vram_peak_mb'], 'Mo')")"
done
note "FIN"
