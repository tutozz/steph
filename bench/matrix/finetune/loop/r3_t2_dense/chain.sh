#!/bin/bash
# R3-T2 partie 2 : Granite 4.0 350M dense, recette R1 de R2-T1 inchangée, seul le corpus change : mix-x4 de la partie 1
# (data/final-x4, composé et vérifié sur cette machine, jamais déplacé) et paires DPO de la partie 1 (152 + 71 de P17 chez R1).
#   chain.sh sft | soup | pairs | dpo | merge <sft-scale>
# SFT LoRA r16 a32 all-linear 3 graines, soupe uniforme, DPO (RPO) 60 pas micro-lot 4, fusion SFT + DPO, GGUF Q4_K_M (b11205).
set -u
STEP=$1
W=/root/steph-ft/loop/r3t2p2; F=$W/repo/bench/matrix/finetune; P1=/root/steph-ft/loop/r3t2p1; D=$P1/mix-x4
PY=/root/steph-ft/venv/bin/python; B=/root/steph-ft/llama.cpp/build/bin; CONV=/root/steph-ft/llama.cpp/convert_hf_to_gguf.py
MODEL=/root/steph-ft/hf-cache/hub/models--ibm-granite--granite-4.0-350m/snapshots/bd8a1497065c0d6ba1ef19af6b0d2b14bacf71c2
SEEDS="42 7 123"
export HF_HOME=/root/steph-ft/hf-cache HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd $W; mkdir -p logs gguf tmp
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
adapters() { for s in $SEEDS; do echo -n "$W/$1-s$s/adapter "; done; }

gguf() {  # dossier HF fusionné, nom ; /tmp de la 3080 ne fait que 1,8 Go, tout passe par $W/tmp
  cp -L $MODEL/config.json $1/config.json
  $PY $CONV $1 --outfile $W/tmp/$2-f16.gguf --outtype f16 --model-name $2 > $W/logs/$2-conv.log 2>&1 || { note "CONVERSION KO $2"; return 1; }
  $B/llama-quantize $W/tmp/$2-f16.gguf $W/gguf/$2-Q4_K_M.gguf Q4_K_M > $W/logs/$2-q.log 2>&1 || { note "QUANT KO $2"; return 1; }
  rm -rf $1 $W/tmp/$2-f16.gguf
}

sft_one() {
  local s=$1 R=$W/sft-s$1
  [ -f $R/adapter/adapter_model.safetensors ] && return 0
  nice -n 5 $PY $F/train_sft.py --model $MODEL --train $D/train.jsonl --val $D/val.jsonl --out $R --mode lora \
    --rank 16 --alpha 32 --lr 2e-4 --epochs 3 --targets all-linear --seed $s --gc --save-adapter --no-merge \
    > $W/logs/sft-s$s.log 2>&1 || { note "SFT KO s$s"; return 1; }
  note "SFT s$s"
}

case $STEP in
  sft)
    for s in ${SFT_SEEDS:-$SEEDS}; do sft_one $s; done ;;
  soup)
    [ -f soup/soup_report.json ] || nice -n 5 $PY $F/soup_adapters.py --model $MODEL --val $D/val.jsonl --out soup \
      --adapters $(for s in $SEEDS; do echo -n "s$s=$W/sft-s$s/adapter "; done) > $W/logs/soup.log 2>&1 || { note "SOUPE KO"; exit 1; }
    [ -f gguf/r3p2-dense-x4-sft-Q4_K_M.gguf ] || gguf soup/merged-uniform r3p2-dense-x4-sft
    note "SOUPE" ;;
  pairs)
    # paires de la partie 1 avant l'ajout des 71 paires P17 (run_k3.sh garde cette base), puis les 71 de P17, comme R1
    [ -f pairs-train.jsonl ] && exit 0
    SRC=$P1/x4/pairs-train.base.jsonl; [ -f $SRC ] || SRC=$P1/x4/pairs-train.jsonl
    cat $SRC /root/steph-ft/p17/pairs-train.jsonl > pairs-train.jsonl && cp $P1/x4/pairs-val.jsonl pairs-val.jsonl
    note "PAIRES $(wc -l < pairs-train.jsonl) train, $(wc -l < pairs-val.jsonl) val" ;;
  dpo)
    N=$(wc -l < pairs-train.jsonl); SPE=$(( (N + 15) / 16 ))
    EP=$(python3 -c "print(round(min(12.0, 60 / $SPE), 2))")
    note "DPO : $N paires, $SPE pas par époque, $EP époques"
    for s in $SEEDS; do
      [ -f dpo-s$s/adapter/adapter_model.safetensors ] || nice -n 5 $PY $F/pref/train_dpo.py --model $MODEL --sft-adapters $(adapters sft) \
        --pairs pairs-train.jsonl --val-pairs pairs-val.jsonl --val $D/val.jsonl --out dpo-s$s --seed $s --lr 2e-5 --epochs $EP --micro 4 \
        > $W/logs/dpo-s$s.log 2>&1 || { note "DPO KO s$s"; exit 1; }
    done
    note "DPO" ;;
  merge)
    L=$2; N=r3p2-dense-x4-l${L/./}
    [ -f gguf/$N-Q4_K_M.gguf ] && exit 0
    nice -n 10 $PY $F/pref/merge_pref.py --base $MODEL --out $W/merged-$N --sft $(adapters sft) --pref $(adapters dpo) --sft-scale $L \
      > $W/logs/$N-merge.log 2>&1 || { note "FUSION KO $N"; exit 1; }
    gguf $W/merged-$N $N && note "GGUF $N $(sha256sum gguf/$N-Q4_K_M.gguf | cut -c1-16)" ;;
  *) echo "usage : $0 sft|soup|pairs|dpo|merge <sft-scale>" >&2; exit 2 ;;
esac
