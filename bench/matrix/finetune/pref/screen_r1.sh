#!/bin/bash
# R1, criblage qualité sur le mix K3 (graine 42, départ P17) : lr 1e-4, lr 5e-5, lr 2e-4 avec la moitié du détail.
set -u
R=/root/steph-ft/r1; F=$R/repo/bench/matrix/finetune; D=/root/steph-ft/k3/mix; PY=/root/steph-ft/venv/bin/python
M=/root/steph-ft/hf-cache/hub/models--ibm-granite--granite-4.0-h-350m/snapshots/3b17b717b8f2f5d305b0a92c1491e239aeda19c8
export HF_HOME=/root/steph-ft/hf-cache HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p $R/logs $R/screen
note() { echo "$(date +%H:%M) $*" >> $R/run.done; }
cd $R
[ -f base-p17/model.safetensors ] || { $PY $F/pref/merge_pref.py --base $M --out base-p17 \
  --sft $(for s in 42 7 123 2024; do echo -n "adapters/p15/runs/granite-s$s/adapter "; done) \
  --pref $(for s in 42 7 123 2024; do echo -n "adapters/p17/runs/p17-dpo-lr2e5-ep12-s$s/adapter "; done) > logs/base-p17.log 2>&1 \
  && cp -L $M/config.json base-p17/config.json; } || { note "BASE KO"; exit 1; }
mkdir -p mix-halfdetail
$PY -c "
import json, hashlib, sys
rows = [json.loads(l) for l in open('$D/train.jsonl')]
keep = [r for r in rows if r['source'] != 'detail' or int(hashlib.sha256(r['messages'][1]['content'].encode()).hexdigest(), 16) % 2 == 0]
open('mix-halfdetail/train.jsonl', 'w').writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in keep)
print(len(rows), len(keep))" > logs/halfdetail.txt
cp $D/val.jsonl mix-halfdetail/val.jsonl
one() {  # nom lr mix
  local O=$R/screen/$1
  [ -f $O/adapter/adapter_model.safetensors ] && return 0
  nice -n 5 $PY $F/train_sft.py --model $R/base-p17 --train $3/train.jsonl --val $3/val.jsonl --out $O --mode lora \
    --rank 16 --alpha 32 --lr $2 --epochs 3 --targets all-linear --seed 42 --gc --save-adapter --no-merge \
    > $R/logs/screen-$1.log 2>&1 || { note "SFT KO $1"; return 1; }
  note "SFT $1"
}
one lr1e4 1e-4 $D
one halfdetail 2e-4 $R/mix-halfdetail
one lr5e5 5e-5 $D
note SCREEN-DONE
