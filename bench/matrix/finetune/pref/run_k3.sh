#!/bin/bash
# K3 : SFT 4 graines -> soupe uniforme -> paires DPO régénérées (juge A7) -> DPO 4 graines -> soupe -> GGUF Q4_K_M.
#   run_k3.sh <étape> <variante> <modèle de départ HF>
#   étapes : sft | soup | pairs | dpo
# Variante a : départ du modèle affiné P17 fusionné ; variante b : départ de la base Granite.
# Suivi : <K>/<variante>/sft-s<graine>/metrics.jsonl et status.json ; arrêt : train_control.sh <hôte> <dossier> stop.
# R1 : MIX (dossier train/val), SFT_LR, TAG (préfixe des GGUF) et EXTRA_PAIRS (paires ajoutées au DPO) ; défauts = K3.
set -u
STEP=$1; V=$2; MODEL=$3
K=${K3:-/root/steph-ft/k3}; F=$K/repo/bench/matrix/finetune; D=${MIX:-$K/mix}; T=${TAG:-k3}
PY=/root/steph-ft/venv/bin/python; B=/root/steph-ft/llama.cpp/build/bin; CONV=/root/steph-ft/llama.cpp/convert_hf_to_gguf.py
QWEN=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf
export HF_HOME=/root/steph-ft/hf-cache HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
W=$K/$V; mkdir -p $W $K/logs; cd $W
SEEDS="42 7 123 2024"
note() { echo "$(date +%H:%M) $*" >> $K/run.done; }

sft_one() {
  local s=$1 R=$W/sft-s$1
  [ -f $R/adapter/adapter_model.safetensors ] && return 0
  nice -n 5 $PY $F/train_sft.py --model $MODEL --train $D/train.jsonl --val $D/val.jsonl --out $R --mode lora \
    --rank 16 --alpha 32 --lr ${SFT_LR:-2e-4} --epochs 3 --targets all-linear --seed $s --gc --save-adapter --no-merge \
    > $K/logs/$V-sft-s$s.log 2>&1 || { note "SFT KO $V s$s"; return 1; }
  note "SFT $V s$s"
}

gguf() {  # dossier HF fusionné, nom
  cp -L $MODEL/config.json $1/config.json
  $PY $CONV $1 --outfile ${F16_DIR:-$W}/$2-f16.gguf --outtype f16 > $K/logs/$2-conv.log 2>&1 || { note "CONVERSION KO $2"; return 1; }
  $B/llama-quantize ${F16_DIR:-$W}/$2-f16.gguf $K/gguf/$2-Q4_K_M.gguf Q4_K_M > $K/logs/$2-q.log 2>&1 || { note "QUANT KO $2"; return 1; }
  rm -rf $1 ${F16_DIR:-$W}/$2-f16.gguf
}

serve() {  # gguf, port, contexte, slots -> PID dans $W/server-<port>.pid
  $B/llama-server -m $1 --host 127.0.0.1 --port $2 -c $3 -ngl 99 --parallel $4 --no-webui --jinja --reasoning-budget 0 \
    > $K/logs/server-$2.log 2>&1 < /dev/null &
  echo $! > $W/server-$2.pid
  for i in $(seq 120); do curl -sf http://127.0.0.1:$2/health >/dev/null && return 0; sleep 2; done
  return 1
}
unserve() { [ -f $W/server-$1.pid ] && kill $(cat $W/server-$1.pid) && rm $W/server-$1.pid; sleep 5; }

adapters() { for s in $SEEDS; do echo -n "$W/$1-s$s/adapter "; done; }

case $STEP in
  sft)
    # deux graines à la fois ; SFT_PAIRS="42,7" pour n'en faire qu'une partie ici (le reste sur une autre machine)
    for pair in ${SFT_PAIRS:-42,7 123,2024}; do
      for s in ${pair//,/ }; do sft_one $s & done; wait
    done ;;
  soup)
    mkdir -p $K/gguf
    [ -f soup/soup_report.json ] || nice -n 5 $PY $F/soup_adapters.py --model $MODEL --val $D/val.jsonl --out soup \
      --adapters $(for s in $SEEDS; do echo -n "s$s=$W/sft-s$s/adapter "; done) > $K/logs/$V-soup.log 2>&1 || { note "SOUPE KO $V"; exit 1; }
    [ -f $K/gguf/$T-$V-sft-Q4_K_M.gguf ] || gguf soup/merged-uniform $T-$V-sft
    note "SOUPE $V" ;;
  pairs)
    serve $K/gguf/$T-$V-sft-Q4_K_M.gguf 8950 16384 8 || { note "SERVEUR SFT KO $V"; exit 1; }
    python3 $F/pref/gen_outputs.py --data $D --port 8950 --out gen.jsonl --seeds 42 7 123 --repeat-penalty 1.0 \
      --max-tokens 160 --parallel 8 > $K/logs/$V-gen.log 2>&1
    unserve 8950
    serve $QWEN 8931 32768 8 || { note "JUGE KO $V"; exit 1; }
    PYTHONPATH=$K/judge:$F/pref python3 $F/pref/judge_outputs.py --data $D --gen gen.jsonl --out verdicts.jsonl --parallel 8 \
      > $K/logs/$V-judge.log 2>&1 || { note "JUGE KO $V"; unserve 8931; exit 1; }
    unserve 8931
    PYTHONPATH=$K/judge:$F/pref python3 $F/pref/build_pairs.py --data $D --gen gen.jsonl --verdicts verdicts.jsonl --out $W \
      > $K/logs/$V-pairs.log 2>&1 || { note "PAIRES KO $V"; exit 1; }
    note "PAIRES $V $(cat pairs-counts.json | tr -d '\n ')" ;;
  dpo)
    # P17 : 71 paires, 12 époques = 60 pas de 16 ; même nombre de pas ici, 12 époques au plus
    [ -n "${EXTRA_PAIRS:-}" ] && [ ! -f pairs-train.base.jsonl ] && { cp pairs-train.jsonl pairs-train.base.jsonl; cat $EXTRA_PAIRS >> pairs-train.jsonl; }
    N=$(wc -l < pairs-train.jsonl); SPE=$(( (N + 15) / 16 ))
    EP=$(python3 -c "print(round(min(12.0, 60 / $SPE), 2))")
    note "DPO $V : $N paires, $SPE pas par époque, $EP époques"
    for s in $SEEDS; do
      R=dpo-s$s
      [ -f $R/adapter/adapter_model.safetensors ] || nice -n 5 $PY $F/pref/train_dpo.py --model $MODEL --sft-adapters $(adapters sft) \
        --pairs pairs-train.jsonl --val-pairs pairs-val.jsonl --val $D/val.jsonl --out $R --seed $s --lr 2e-5 --epochs $EP \
        > $K/logs/$V-dpo-s$s.log 2>&1 || { note "DPO KO $V s$s"; exit 1; }
    done
    [ -f $K/gguf/$T-$V-dpo-Q4_K_M.gguf ] || {
      nice -n 10 $PY $F/pref/merge_pref.py --base $MODEL --out merged-dpo --sft $(adapters sft) --pref $(adapters dpo) \
        > $K/logs/$V-dpo-merge.log 2>&1 || { note "FUSION KO $V"; exit 1; }
      gguf merged-dpo $T-$V-dpo; }
    note "GGUF $V" ;;
  *) echo "usage : $0 sft|soup|pairs|dpo <variante> <modèle>" >&2; exit 2 ;;
esac
