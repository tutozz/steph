#!/bin/bash
# R2-C1 : paires DPO à inventions injectées sur R1, 3080 partagée (portes VRAM), reprise par étape.
#   r2c1.sh <variante> <époques>
set -u
V=${1:-e1}; EP=${2:-1}
W=/root/steph-ft/loop/r2c1; C=$W/code; B=/root/steph-ft/llama.cpp/build/bin; PY=/root/steph-ft/venv/bin/python
R1G=/root/steph-ft/r1/gguf/steph-speak-granite-4.0-h-350M-dpo-v1.0-Q4_K_M.gguf
QWEN=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf
export HF_HOME=/root/steph-ft/hf-cache HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export JUDGE_PORT=8981 PYTHONPATH=$C/judge:$C
cd $W; mkdir -p runs judge logs gguf
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
vram() { while :; do f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); [ "$f" -ge $1 ] && return 0; sleep 60; done; }
disk() { f=$(df --output=avail -m / | tail -1); [ "$f" -ge $1 ] || { note "DISQUE $f Mo < $1 Mo, arrêt"; exit 1; }; }
bench() {  # gguf, nom
  for sd in 7 42 123; do
    OUT=runs/$2-dev-b$sd.json
    [ -f $OUT ] && continue
    vram 1500
    python3 $C/bench_run.py --server $B/llama-server --model $1 --label $2-v3dev-b$sd --cases $C/dev.json --maxc 0 \
      --port 8972 --ngl 99 --payload "{\"seed\": $sd}" --out $OUT >> logs/bench-$2.log 2>&1 || note "BANC KO $2 b$sd"
  done
  note "BANC $2"
}
qwen_up() {
  vram 7200
  $B/llama-server -m $QWEN --host 127.0.0.1 --port 8981 -c 32768 -ngl 99 --parallel 4 --no-webui --jinja --reasoning-budget 0 \
    > logs/qwen.log 2>&1 < /dev/null &
  echo $! > logs/qwen.pid
  for i in $(seq 120); do curl -sf http://127.0.0.1:8981/health >/dev/null && return 0; sleep 2; done
  note "QWEN KO"; qwen_down; return 1
}
qwen_down() { [ -f logs/qwen.pid ] && kill $(cat logs/qwen.pid) && rm logs/qwen.pid; sleep 5; }
validate() {  # sortie
  [ -f $1 ] && return 0
  python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json $1 > logs/$(basename $1 .json).log 2>&1
  local rc=$?; note "VALIDATION $(basename $1) rc=$rc"; return $rc
}

# 0. génération on-policy finie, serveur R1 arrêté
while pgrep -f "code/gen_outputs.py --data onpol" > /dev/null; do sleep 30; done
[ -f logs/server-8971.pid ] && { kill $(cat logs/server-8971.pid); rm logs/server-8971.pid; }
# 1. R1 rebanqué sur dev
bench $R1G r1
# 2. juge : validation, on-policy, contrôle des injections
if [ ! -f onpol/pairs-train.jsonl ] || [ ! -f judge/inject-control.json ]; then
  qwen_up || exit 1
  validate judge/validate-pre-A.json || { note "JUGE NON VALIDÉ"; qwen_down; exit 1; }
  python3 $C/j.py $C/judge_outputs.py --data onpol/data --gen onpol/gen.jsonl --out onpol/verdicts.jsonl --parallel 4 > logs/onpol-judge.log 2>&1 \
    && python3 $C/build_pairs.py --data onpol/data --gen onpol/gen.jsonl --verdicts onpol/verdicts.jsonl --out onpol --max-per-prompt 2 > logs/onpol-pairs.log 2>&1 \
    || { note "ONPOL KO"; qwen_down; exit 1; }
  python3 $C/j.py $C/judge_injected.py --pairs pairs/inject/pairs-train.jsonl --n 50 --out judge/inject-control.json > logs/inject-control.log 2>&1 || note "CONTRÔLE KO"
  qwen_down
  note "PAIRES ONPOL $(tr -d "\n " < onpol/pairs-counts.json) ; CONTRÔLE $(tail -1 logs/inject-control.log)"
fi
# 3. paires
cat pairs/inject/pairs-train.jsonl onpol/pairs-train.jsonl > pairs/train.jsonl
cat pairs/inject/pairs-val.jsonl onpol/pairs-val.jsonl > pairs/val.jsonl
# 4. DPO sur R1, 2 graines
for s in 42 7; do
  D=$V/dpo-s$s
  [ -f $D/adapter/adapter_model.safetensors ] && continue
  for try in 1 2 3 4 5 6; do
    vram 4000
    nice -n 5 $PY $C/train_dpo.py --model $W/r1-hf --pairs pairs/train.jsonl --val-pairs pairs/val.jsonl \
      --val /root/steph-ft/r1/mix-i1/val.jsonl --out $D --seed $s --lr 2e-5 --epochs $EP --micro 2 > logs/$V-dpo-s$s.log 2>&1 && break
    note "DPO KO $V s$s essai $try"; sleep 120
  done
  [ -f $D/adapter/adapter_model.safetensors ] || { note "DPO ABANDON $V s$s"; exit 1; }
  note "DPO $V s$s"
done
# 5. soupe et GGUF
G=gguf/r2c1-$V-Q4_K_M.gguf
if [ ! -f $G ]; then
  disk 2500
  nice -n 10 $PY $C/merge_pref.py --base $W/r1-hf --out $W/merged-$V --sft $V/dpo-s42/adapter $V/dpo-s7/adapter > logs/$V-merge.log 2>&1 \
    && cp $W/r1-hf/config.json $W/merged-$V/config.json \
    && nice -n 10 $PY /root/steph-ft/llama.cpp/convert_hf_to_gguf.py $W/merged-$V --outfile /tmp/r2c1-$V-f16.gguf --outtype f16 > logs/$V-conv.log 2>&1 \
    && $B/llama-quantize /tmp/r2c1-$V-f16.gguf $G Q4_K_M > logs/$V-q.log 2>&1 || { note "GGUF KO $V"; exit 1; }
  rm -rf $W/merged-$V /tmp/r2c1-$V-f16.gguf
  note "GGUF $V $(sha256sum $G | cut -c1-16) $(stat -c %s $G)"
fi
# 6. banc du candidat
bench $G r2c1-$V
# 7. juge sur la graine 7, R1 et candidat dans la même session, validation avant et après
if [ ! -f judge/v3dev-$V-done ]; then
  qwen_up || exit 1
  validate judge/validate-pre-$V.json || { note "JUGE NON VALIDÉ $V"; qwen_down; exit 1; }
  python3 $C/j.py $C/judge_v3.py $C/dev.json judge/v3dev-$V.json runs/r1-dev-b7.json runs/r2c1-$V-dev-b7.json > logs/judge-$V.log 2>&1 \
    || { note "JUGE KO $V"; qwen_down; exit 1; }
  validate judge/validate-post-$V.json
  qwen_down
  touch judge/v3dev-$V-done
  note "JUGE $V $(tail -1 logs/judge-$V.log)"
fi
note "FIN $V"
