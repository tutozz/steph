#!/bin/bash
# R2-C1, ablation : DPO sur les seules paires injectées (pas d on-policy), pendant que le juge attend la VRAM.
set -u
V=inj; W=/root/steph-ft/loop/r2c1; C=$W/code; B=/root/steph-ft/llama.cpp/build/bin; PY=/root/steph-ft/venv/bin/python
export HF_HOME=/root/steph-ft/hf-cache HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd $W
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
vram() { while :; do f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); [ "$f" -ge $1 ] && return 0; sleep 60; done; }
for s in 42 7; do
  D=$V/dpo-s$s
  for try in 1 2 3 4 5 6; do
    [ -f $D/adapter/adapter_model.safetensors ] && break
    vram 2800
    nice -n 5 $PY $C/train_dpo.py --model $W/r1-hf --pairs pairs/inject/pairs-train.jsonl --val-pairs pairs/inject/pairs-val.jsonl \
      --val /root/steph-ft/r1/mix-i1/val.jsonl --out $D --seed $s --lr 2e-5 --epochs 1 --micro 2 > logs/$V-dpo-s$s.log 2>&1 && break
    note "DPO KO $V s$s essai $try"; sleep 120
  done
  [ -f $D/adapter/adapter_model.safetensors ] || { note "DPO ABANDON $V"; exit 1; }
  note "DPO $V s$s $(python3 -c "import json;d=json.load(open(\"$D/train_log.json\"));print(d[\"steps\"],d[\"vram_peak_mb\"],d[\"evals\"][0],d[\"evals\"][-1])")"
done
G=gguf/r2c1-$V-Q4_K_M.gguf
if [ ! -f $G ]; then
  f=$(df --output=avail -m / | tail -1); [ "$f" -ge 2500 ] || { note "DISQUE $f Mo"; exit 1; }
  nice -n 10 $PY $C/merge_pref.py --base $W/r1-hf --out $W/merged-$V --sft $V/dpo-s42/adapter $V/dpo-s7/adapter > logs/$V-merge.log 2>&1 \
    && cp $W/r1-hf/config.json $W/merged-$V/config.json \
    && nice -n 10 $PY /root/steph-ft/llama.cpp/convert_hf_to_gguf.py $W/merged-$V --outfile /tmp/r2c1-$V-f16.gguf --outtype f16 > logs/$V-conv.log 2>&1 \
    && $B/llama-quantize /tmp/r2c1-$V-f16.gguf $G Q4_K_M > logs/$V-q.log 2>&1 || { note "GGUF KO $V"; exit 1; }
  rm -rf $W/merged-$V /tmp/r2c1-$V-f16.gguf
  note "GGUF $V $(sha256sum $G | cut -c1-16) $(stat -c %s $G)"
fi
for sd in 7 42 123; do
  OUT=runs/r2c1-$V-dev-b$sd.json; [ -f $OUT ] && continue
  vram 1500
  python3 $C/bench_run.py --server $B/llama-server --model $G --label r2c1-$V-v3dev-b$sd --cases $C/dev.json --maxc 0 \
    --port 8973 --ngl 99 --payload "{\"seed\": $sd}" --out $OUT >> logs/bench-r2c1-$V.log 2>&1 || note "BANC KO $V b$sd"
done
note "BANC r2c1-$V"
