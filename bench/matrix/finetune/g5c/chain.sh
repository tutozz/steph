#!/bin/bash
# G5c : recette a-sft de G5 à l'identique sur les étiquettes T9, pour isoler leur effet (G5b manquait du mix-extra de R1).
# Granite 4.0 H 350M depuis P17 fusionné, SFT LoRA de run_k3.sh (rang 16, lr 2e-4, 3 époques), 4 graines, soupe uniforme,
# GGUF Q4_K_M ; mix = chaîne R1 sur final-t9 + mix-extra de R1 (ft/data/mix-extra-r1, sha256 identiques à ceux de la 3080)
# + correctif de langue x2 + final-t9-corrections x1, contamination par ligne. Sur l'hôte de la 3060 (final-t9 n'en sort pas).
# Seul écart restant avec a-sft hors étiquettes : le correctif de langue de G5 vit sur la 3080 ; celui de G3b de cette
# machine (même recette g3b_langfix.py) le remplace, comme dans G5b.
#   chain.sh mix | sft | soup
# Tout sous nice 19. La carte est partagée : l'entraînement Gemma de G3c (train-t9-3060.sh) passe d'abord, puis une graine
# à la fois avec 7 Go libres. Base P17, Python 3.13 et pylib (noyaux Triton de mamba_ssm) repris de g5b.
set -u
STEP=$1
T=/mnt/backup-hdd/stephbench-tmp; W=$T/g5c; G5B=$T/g5b; R=$W/repo; F=$R/bench/matrix/finetune; D=$T/ft/data
PY=$T/ft/venv/bin/python; LB=/root/stephbench-matrix/bin/vulkan/llama-b11205; CONV=$T/ft/llama.cpp/convert_hf_to_gguf.py
PY3=$G5B/py/cpython-3.13.15-linux-x86_64-gnu/bin/python3.13  # src/steph exige 3.12+ ; python3 de l'hôte : 3.11
BASE=$G5B/base-p17; LANGFIX=$T/gemma/g3b/work/langfix.jsonl; CORR=$D/final-t9-corrections/sft.jsonl; EXTRA=$D/mix-extra-r1
EXTRA_SHA="5a51360159516467ffb489ab1fe908531e7ab2b07f0d6a42baf37740cac5dd1a cb39f6886f9b3db5f91e76f167247874ddb3818a65cf4500b4df8cc0c74e15ce"
# sans mamba_ssm, transformers prend le balayage torch de référence, qui demande 24 Go sur la validation
export PYTHONPATH=$G5B/pylib HF_HOME=$T/ft/cache/hf HF_HUB_OFFLINE=1 TMPDIR=$T/ft/cache/tmp PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
note() { echo "$(date '+%d %H:%M') $*" >> $W/run.done; }
card_free() {
  while pgrep -f train-t9-3060.sh > /dev/null; do sleep 120; done
  until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge 7000 ]; do sleep 60; done
}
SEEDS="42 7 123 2024"
mkdir -p $W/logs $W/gguf; cd $W

case $STEP in
  mix)
    [ -f $W/mix/train.jsonl ] && exit 0
    [ "$(sha256sum $EXTRA/train.jsonl $EXTRA/val.jsonl | cut -d' ' -f1 | paste -sd' ')" = "$EXTRA_SHA" ] \
      || { note "ARRÊT : mix-extra-r1 différent de celui de R1"; exit 1; }
    X=$W/x4r1; mkdir -p $X $W/clean $W/mix
    ( cd $D && cat final-t9/macos.jsonl final-t9/linux-low.jsonl final-t9/linux-dev.jsonl final-t9/snapshot-linux-dev.jsonl \
        final-t9/snapshot-linux-low.jsonl > $X/fr.jsonl
      nice -n 19 $PY3 $F/fix_labels.py $X/fr.jsonl $X/fr.fixed.jsonl
      nice -n 19 $PY3 $F/compose_train.py $X/fr.fixed.jsonl $X/fr-mix --cap 250 --bench $R/bench/matrix/cases.json
      PYTHONPATH=$R/src nice -n 19 $PY3 $F/compose_k3.py --fr-mix $X/fr-mix --fr-raw corpus/*.jsonl snapshot-1/clean/*.jsonl \
        --en final-t9/macos.en.jsonl final-t9/linux-low.en.jsonl --en-raw corpus/*.en.jsonl \
        --feature detail=final-t9/detail.jsonl --feature start=final/start.jsonl --feature progress=final-t9/progress.jsonl \
        --feature flux=final-t9/flux.jsonl --feature summary_residual=final/summary_residual.jsonl --feature-raw corpus/features-*.jsonl \
        --qa final-t9/qa_train.jsonl --bench $R/bench/matrix/cases.json --speak-bench $R/benchmark/data/v1 --max-chars 587 \
        --out $X/k3mix > $W/logs/k3mix.json
      nice -n 19 $PY3 $F/compose_r1.py --base $X/k3mix --extra $EXTRA --repeat en_summary=2 --keep detail=0.5 \
        --out $W/mix-t9r1 > $W/logs/mix-t9r1.json ) || { note "MIX KO"; exit 1; }
    $PY3 $R/bench/matrix/v3/tools/leak_check.py prints $W/v3prints-head.json $R/bench/matrix/v3/cases/*.jsonl \
      $R/bench/matrix/v3/cases/dev/*.jsonl $R/bench/matrix/v3/cases/test/*.jsonl > /dev/null
    cp $LANGFIX $W/langfix.jsonl; cp $CORR $W/corrections.jsonl
    for f in langfix corrections mix-t9r1/train mix-t9r1/val; do
      n=$(echo $f | tr / -)
      $PY3 $R/bench/matrix/v3/tools/leak_check.py drop $W/v3prints-head.json $W/$f.jsonl $W/clean/$n.jsonl > $W/logs/drop-$n.log
      note "SANS FUITE $f $(cut -c1-120 $W/logs/drop-$n.log)"
    done
    cat $W/clean/mix-t9r1-train.jsonl $W/clean/langfix.jsonl $W/clean/langfix.jsonl $W/clean/corrections.jsonl > $W/mix/train.jsonl
    cp $W/clean/mix-t9r1-val.jsonl $W/mix/val.jsonl
    # audit_pii à 0 : toute ligne signalée sort
    for f in train val; do
      bad=$($PY3 $F/audit_pii.py --details $W/mix/$f.jsonl | grep -o "$f.jsonl:[0-9]*" | cut -d: -f2 | sort -u | sed 's/$/d/' | paste -sd';')
      [ -n "$bad" ] && sed -i "$bad" $W/mix/$f.jsonl && note "PII $f : lignes retirées ${bad//d/}"
    done
    $PY3 $F/audit_pii.py $W/mix/train.jsonl $W/mix/val.jsonl > $W/logs/pii-mix.log 2>&1 || { note "ARRÊT : audit_pii $(tail -1 $W/logs/pii-mix.log)"; exit 1; }
    $PY3 $R/bench/matrix/v3/tools/leak_check.py scan $W/v3prints-head.json $W/logs/leak-mix.json $W/mix/train.jsonl $W/mix/val.jsonl \
      > $W/logs/leak-mix.log 2>&1
    sha256sum $W/mix-t9r1/*.jsonl $W/mix/*.jsonl $W/langfix.jsonl $W/corrections.jsonl > $W/logs/mix-sha.txt
    rm -rf $X $W/langfix.jsonl $W/corrections.jsonl
    note "MIX $(wc -l < $W/mix/train.jsonl) / $(wc -l < $W/mix/val.jsonl) ; fuite $(tail -1 $W/logs/leak-mix.log | cut -c1-80)" ;;
  sft)  # train_sft.py aux arguments de run_k3.sh (sft_one), une graine à la fois
    grep -q '"rejected": \[\]' $W/logs/leak-mix.log || { note "ARRÊT : cas du banc dans le mix"; exit 1; }
    for s in $SEEDS; do
      O=$W/a/sft-s$s
      [ -f $O/adapter/adapter_model.safetensors ] && continue
      card_free; note "SFT départ s$s"
      nice -n 19 $PY $F/train_sft.py --model $BASE --train $W/mix/train.jsonl --val $W/mix/val.jsonl --out $O --mode lora \
        --rank 16 --alpha 32 --lr 2e-4 --epochs 3 --targets all-linear --seed $s --gc --save-adapter --no-merge \
        > $W/logs/sft-s$s.log 2>&1 || { note "SFT KO s$s $(tail -1 $W/logs/sft-s$s.log | cut -c1-120)"; exit 1; }
      note "SFT s$s $(tail -2 $W/logs/sft-s$s.log | head -1)"
    done ;;
  soup)  # soupe uniforme (soup_adapters.py de run_k3.sh), GGUF Q4_K_M (conversion 9588757, quantification b11205)
    N=g5c-sft; [ -f $W/gguf/$N-Q4_K_M.gguf ] && exit 0
    card_free
    [ -f $W/a/soup/soup_report.json ] || nice -n 19 $PY $F/soup_adapters.py --model $BASE --val $W/mix/val.jsonl --out $W/a/soup \
      --adapters $(for s in $SEEDS; do echo -n "s$s=$W/a/sft-s$s/adapter "; done) > $W/logs/soup.log 2>&1 || { note "SOUPE KO"; exit 1; }
    M=$W/a/soup/merged-uniform; cp -L $BASE/config.json $M/config.json
    nice -n 19 $PY $CONV $M --outfile $W/gguf/$N-f16.gguf --outtype f16 > $W/logs/$N-conv.log 2>&1 \
      && LD_LIBRARY_PATH=$LB nice -n 19 $LB/llama-quantize $W/gguf/$N-f16.gguf $W/gguf/$N-Q4_K_M.gguf Q4_K_M > $W/logs/$N-q.log 2>&1 \
      || { note "GGUF KO"; exit 1; }
    rm -rf $M $W/gguf/$N-f16.gguf
    note "GGUF $N $(sha256sum $W/gguf/$N-Q4_K_M.gguf | cut -c1-16) $(stat -c %s $W/gguf/$N-Q4_K_M.gguf)" ;;
  all) bash $0 mix && bash $0 sft && bash $0 soup ;;
  *) echo "usage : chain.sh mix|sft|soup|all" >&2; exit 2 ;;
esac
