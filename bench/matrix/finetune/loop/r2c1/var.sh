#!/bin/bash
# R2-C1, variante : DPO sur R1 (2 graines) avec un jeu de paires donné, soupe, fusion à une ou plusieurs échelles, GGUF, banc dev.
#   var.sh <nom> <paires train> <paires val> <époques> <échelle...>
set -u
V=$1; PT=$2; PV=$3; EP=$4; shift 4
W=/root/steph-ft/loop/r2c1; C=$W/code; B=/root/steph-ft/llama.cpp/build/bin; PY=/root/steph-ft/venv/bin/python
export HF_HOME=/root/steph-ft/hf-cache HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd $W
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
vram() { while :; do f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); [ "$f" -ge $1 ] && return 0; sleep 60; done; }
for s in 42 7; do
  D=$V/dpo-s$s
  for try in 1 2 3 4 5 6 7 8; do
    [ -f $D/adapter/adapter_model.safetensors ] && break
    vram 2800
    nice -n 5 $PY $C/train_dpo.py --model $W/r1-hf --pairs $PT --val-pairs $PV \
      --val /root/steph-ft/r1/mix-i1/val.jsonl --out $D --seed $s --lr 2e-5 --epochs $EP --micro 2 > logs/$V-dpo-s$s.log 2>&1 && break
    note "DPO KO $V s$s essai $try"; sleep 120
  done
  [ -f $D/adapter/adapter_model.safetensors ] || { note "DPO ABANDON $V"; exit 1; }
  note "DPO $V s$s $(python3 -c "import json;d=json.load(open(\"$D/train_log.json\"));print(d[\"steps\"],d[\"vram_peak_mb\"],d[\"evals\"][0],d[\"evals\"][-1])")"
done
for L in "$@"; do
  N=r2c1-$V-l${L/./}
  G=gguf/$N-Q4_K_M.gguf
  if [ ! -f $G ]; then
    f=$(df --output=avail -m / | tail -1); [ "$f" -ge 1800 ] || { note "DISQUE $f Mo"; exit 1; }
    nice -n 10 $PY $C/merge_pref.py --base $W/r1-hf --out /dev/shm/r2c1-merged-$N --sft $V/dpo-s42/adapter $V/dpo-s7/adapter --sft-scale $L > logs/$N-merge.log 2>&1 \
      && cp $W/r1-hf/config.json /dev/shm/r2c1-merged-$N/config.json \
      && nice -n 10 $PY /root/steph-ft/llama.cpp/convert_hf_to_gguf.py /dev/shm/r2c1-merged-$N --outfile /dev/shm/r2c1-$N-f16.gguf --outtype f16 > logs/$N-conv.log 2>&1 \
      && $B/llama-quantize /dev/shm/r2c1-$N-f16.gguf $G Q4_K_M > logs/$N-q.log 2>&1 || { note "GGUF KO $N"; rm -rf /dev/shm/r2c1-merged-$N /dev/shm/r2c1-$N-f16.gguf; exit 1; }
    rm -rf /dev/shm/r2c1-merged-$N /dev/shm/r2c1-$N-f16.gguf
    note "GGUF $N $(sha256sum $G | cut -c1-16) $(stat -c %s $G)"
  fi
  for sd in 7 42 123; do
    OUT=runs/$N-dev-b$sd.json; [ -f $OUT ] && continue
    vram 1500
    python3 $C/bench_run.py --server $B/llama-server --model $G --label $N-v3dev-b$sd --cases $C/dev.json --maxc 0 \
      --port 8974 --ngl 99 --payload "{\"seed\": $sd}" --out $OUT >> logs/bench-$N.log 2>&1 || note "BANC KO $N b$sd"
  done
  note "BANC $N"
done
