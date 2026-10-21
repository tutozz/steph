#!/bin/bash
# R3-T3 : enseignant Granite 4.1-3B (même tokeniseur que Granite H 350M, octet pour octet), puis distillation.
#   chain.sh teacher <seed> | teacher-gguf <seed> | bench <label> <gguf> [seeds...]
#   élève (recette R1 depuis P17, bras kd = KL top-32 + CE alpha 0,5 T 1,0 ; bras ce = même code, alpha 0) :
#   chain.sh topk | ssft <bras> <seed> | ssoup <bras> | spairs <bras> | sdpo <bras>
# Tout sur la 3060, nice -n 19, sous /mnt/backup-hdd/stephbench-tmp/loop/r3t3 ; le mix ne quitte pas l'hôte.
set -u
STEP=$1; shift
W=/mnt/backup-hdd/stephbench-tmp/loop/r3t3; R=$W/repo; F=$R/bench/matrix/finetune
source /mnt/backup-hdd/stephbench-tmp/ft/env.sh
PY=$FT/venv/bin/python; LB=/root/stephbench-matrix/bin/vulkan/llama-b11205; CONV=$FT/llama.cpp/convert_hf_to_gguf.py
T=$W/hf/granite-4.1-3b; D=$W/work/mix-x4r1
# pylib : bitsandbytes, mamba_ssm (balayage Triton, sans lui le chemin torch demande 24 Go), einops
export HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True PYTHONPATH=$R/src:$W/pylib
K=$R/bench/matrix/finetune/loop/r3t3
P=/mnt/backup-hdd/stephbench-tmp/r2c3/work/base-p17; SEEDS="42 7 123 2024"
QWEN=/mnt/backup-hdd/stephbench-tmp/models/Qwen3.5-9B-Q4_K_M.gguf
cd $W
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }

gguf() {  # dossier HF, nom
  nice -n 19 $PY $CONV $1 --outfile $W/work/$2-f16.gguf --outtype f16 --model-name $2 > $W/logs/$2-conv.log 2>&1 || { note "CONVERSION KO $2"; return 1; }
  nice -n 19 $LB/llama-quantize $W/work/$2-f16.gguf $W/gguf/$2-Q4_K_M.gguf Q4_K_M > $W/logs/$2-q.log 2>&1 || { note "QUANT KO $2"; return 1; }
  rm -f $W/work/$2-f16.gguf
  note "GGUF $2 $(sha256sum $W/gguf/$2-Q4_K_M.gguf | cut -c1-16) $(stat -c %s $W/gguf/$2-Q4_K_M.gguf)"
}

case $STEP in
  teacher)  # recette R1 : LoRA r16 a32 all-linear, lr 2e-4, 3 époques, arrêt anticipé patience 3
    # QLoRA NF4 : la 3060 porte un juge 9B d'une autre théorie (7,4 Go), 4,8 Go restent
    s=$1; O=$W/work/teacher-s$s
    [ -f $O/train_log.json ] && exit 0
    nice -n 19 $PY $K/train_kd.py --model $T --train $D/train.jsonl --val $D/val.jsonl --out $O \
      --mode lora --qlora --no-merge --kd-alpha 0 --rank 16 --alpha 32 --lr 2e-4 --epochs 3 --targets all-linear --seed $s --gc \
      --save-adapter --micro ${MICRO:-2} > $W/logs/teacher-s$s.log 2>&1 && note "ENSEIGNANT s$s" || note "ENSEIGNANT KO s$s" ;;
  teacher-gguf)  # fusion en bf16 sur CPU, puis GGUF
    s=$1; N=r3t3-teacher-s$s; M=$W/work/teacher-s$s/merged
    [ -f $W/gguf/$N-Q4_K_M.gguf ] && exit 0
    CUDA_VISIBLE_DEVICES= nice -n 19 $PY $K/merge_lora.py --base $T --adapter $W/work/teacher-s$s/adapter --out $M > $W/logs/$N-merge.log 2>&1 \
      || { note "FUSION KO $N"; exit 1; }
    gguf $M $N && rm -rf $M ;;
  bench)  # banc v3 dev, graines données (défaut 7 42 123), Vulkan b11205, même harnais que R1
    L=$1; G=$2; shift 2
    sha256sum $G >> $W/gguf-sha256.txt
    P0=897; [[ $L == ce-* ]] && P0=896  # deux bancs peuvent tourner en même temps : ports distincts
    for sd in ${@:-7 42 123}; do
      O=$W/runs/$L-dev-b$sd.json
      [ -f $O ] || nice -n 19 python3 $R/bench/matrix/bench_run.py --server $LB/llama-server --model $G --label $L-v3dev-b$sd \
        --cases $R/bench/matrix/v3/harness/dev.json --maxc 0 --port $P0${sd: -1} --ngl 99 --payload "{\"seed\": $sd}" \
        --out $O >> $W/logs/bench-$L.log 2>&1
    done
    note "BANC $L" ;;
  topk)  # logits top-32 de l'enseignant s42 (base NF4 + adaptateur, l'objet entraîné) sur train et val du mix
    [ -f $W/work/topk-s42.pt ] && exit 0
    nice -n 19 $PY $K/extract_topk.py --teacher $T --adapter $W/work/teacher-s42/adapter --qlora --tok $P \
      --data $D/train.jsonl $D/val.jsonl --out $W/work/topk-s42.pt --k 32 > $W/logs/topk.log 2>&1 \
      && note "TOPK $(tail -1 $W/logs/topk.log)" || { note "TOPK KO"; exit 1; } ;;
  ssft)  # SFT recette R1 (run_k3.sh sft_one) sur P17 ; seul change le terme KD
    b=$1; s=$2; O=$W/$b/sft-s$s
    [ -f $O/adapter/adapter_model.safetensors ] && exit 0
    # verrou : deux pilotes peuvent viser la même graine ; le second attend l'adaptateur du premier
    mkdir -p $W/$b; mkdir $O.lock 2>/dev/null || { until [ -f $O/adapter/adapter_model.safetensors ]; do sleep 60; done; exit 0; }
    KDA=0; [ $b = kd ] && KDA=0.5
    nice -n 19 $PY $K/train_kd.py --model $P --train $D/train.jsonl --val $D/val.jsonl --out $O --mode lora \
      --rank 16 --alpha 32 --lr 2e-4 --epochs 3 --targets all-linear --seed $s --gc --save-adapter --no-merge \
      --kd $W/work/topk-s42.pt --kd-alpha $KDA --kd-temp 1.0 > $W/logs/$b-sft-s$s.log 2>&1 && note "SFT $b s$s" || { note "SFT KO $b s$s"; exit 1; } ;;
  ssoup)  # soupe uniforme des 4 graines (run_k3.sh soup), GGUF
    b=$1; N=r3t3-$b-sft; cd $W/$b
    [ -f soup/soup_report.json ] || nice -n 19 $PY $F/soup_adapters.py --model $P --val $D/val.jsonl --out soup \
      --adapters $(for s in $SEEDS; do echo -n "s$s=$W/$b/sft-s$s/adapter "; done) > $W/logs/$b-soup.log 2>&1 || { note "SOUPE KO $b"; exit 1; }
    [ -f $W/gguf/$N-Q4_K_M.gguf ] || { cp -L $P/config.json soup/merged-uniform/config.json; gguf soup/merged-uniform $N && rm -rf soup/merged-uniform; } ;;
  spairs)  # paires DPO régénérées (run_k3.sh pairs) : sorties de la soupe SFT jugées par A7 sur le juge 9B de cet hôte
    b=$1; cd $W/$b; JP=${JPORT:-8931}
    [ -f pairs-counts.json ] && exit 0
    $LB/llama-server -m $W/gguf/r3t3-$b-sft-Q4_K_M.gguf --host 127.0.0.1 --port 8950 -c 16384 -ngl 99 --parallel 8 --no-webui --jinja \
      --reasoning-budget 0 > $W/logs/$b-gen-server.log 2>&1 < /dev/null & SP=$!
    until curl -sf http://127.0.0.1:8950/health >/dev/null; do sleep 2; done
    python3 $F/pref/gen_outputs.py --data $D --port 8950 --out gen.jsonl --seeds 42 7 123 --repeat-penalty 1.0 \
      --max-tokens 160 --parallel 8 > $W/logs/$b-gen.log 2>&1
    kill $SP; sleep 5
    JS=
    if ! curl -sf http://127.0.0.1:$JP/health >/dev/null; then  # juge 9B propre à cette étape, arrêté par son PID
      nice -n 19 $LB/llama-server -m $QWEN --host 127.0.0.1 --port $JP -c 32768 --parallel 8 -ngl 99 --jinja --no-webui \
        > $W/logs/judge-$JP.log 2>&1 < /dev/null & JS=$!
      until curl -sf http://127.0.0.1:$JP/health >/dev/null; do kill -0 $JS 2>/dev/null || { note "JUGE KO $b"; exit 1; }; sleep 3; done
    fi
    mkdir -p $W/judge; sed "s/^PORT = 8931/PORT = $JP/" $F/judge_lib_a7.py > $W/judge/judge_lib.py
    PYTHONPATH=$W/judge:$F/pref python3 $F/pref/judge_outputs.py --data $D --gen gen.jsonl --out verdicts.jsonl --parallel 8 \
      > $W/logs/$b-judge.log 2>&1 || { note "JUGE KO $b"; [ -n "$JS" ] && kill $JS; exit 1; }
    [ -n "$JS" ] && kill $JS
    PYTHONPATH=$W/judge:$F/pref python3 $F/pref/build_pairs.py --data $D --gen gen.jsonl --verdicts verdicts.jsonl --out $W/$b \
      > $W/logs/$b-pairs.log 2>&1 || { note "PAIRES KO $b"; exit 1; }
    note "PAIRES $b $(tr -d '\n ' < pairs-counts.json)" ;;
  sdpo)  # DPO 4 graines (run_k3.sh dpo, sans les 71 paires P17 absentes de cet hôte), fusion SFT 0,7 comme v1.0
    b=$1; cd $W/$b; N=r3t3-$b-l07
    n=$(wc -l < pairs-train.jsonl); SPE=$(( (n + 15) / 16 )); EP=$(python3 -c "print(round(min(12.0, 60 / $SPE), 2))")
    note "DPO $b : $n paires, $EP époques"
    ad() { for s in $SEEDS; do echo -n "$W/$b/$1-s$s/adapter "; done; }
    for s in $SEEDS; do
      [ -f dpo-s$s/adapter/adapter_model.safetensors ] || nice -n 19 $PY $F/pref/train_dpo.py --model $P --sft-adapters $(ad sft) \
        --pairs pairs-train.jsonl --val-pairs pairs-val.jsonl --val $D/val.jsonl --out dpo-s$s --seed $s --lr 2e-5 --epochs $EP \
        > $W/logs/$b-dpo-s$s.log 2>&1 || { note "DPO KO $b s$s"; exit 1; }
    done
    [ -f $W/gguf/$N-Q4_K_M.gguf ] || { nice -n 19 $PY $F/pref/merge_pref.py --base $P --out merged-l07 --sft $(ad sft) --pref $(ad dpo) \
      --sft-scale 0.7 > $W/logs/$N-merge.log 2>&1 || { note "FUSION KO $N"; exit 1; }
      cp -L $P/config.json merged-l07/config.json; gguf merged-l07 $N && rm -rf merged-l07; } ;;
  *) echo "usage : $0 teacher <seed> | teacher-gguf <seed> | bench <label> <gguf> [seeds]" >&2; exit 2 ;;
esac
