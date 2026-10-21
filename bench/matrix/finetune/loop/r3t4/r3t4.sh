#!/bin/bash
# R3-T4 partie 2, sur l'hôte du corpus R1 (3080 partagée : portes VRAM, reprise par étape).
#   r3t4.sh r1hf | judge | dpo <variante> [époques] | bench <gguf> <nom> | judgebench <sortie> <run...>
# Rien ne quitte la machine : sorties on-policy, verdicts, paires et adaptateurs restent sous $W.
set -u
W=/root/steph-ft/loop/r3t4; C=$W/code; B=/root/steph-ft/llama.cpp/build/bin; PY=/root/steph-ft/venv/bin/python
R=/root/steph-ft/r1; QWEN=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf
export HF_HOME=/root/steph-ft/hf-cache HF_HUB_OFFLINE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export JUDGE_PORT=8983 PYTHONPATH=$C/judge:$C
cd $W; mkdir -p logs judge runs gguf
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
vram() { while :; do f=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); [ "$f" -ge $1 ] && return 0; sleep 10; done; }
disk() { f=$(df --output=avail -m / | tail -1); [ "$f" -ge $1 ] || { note "DISQUE $f Mo < $1 Mo, arrêt"; exit 1; }; }
qwen_up() {  # validation 6/6 avant
  vram 6400  # 4 096 jetons par fente : à 2 048, 22 entrées longues du corpus dépassaient ; 3080 partagée
  $B/llama-server -m $QWEN --host 127.0.0.1 --port $JUDGE_PORT -c 16384 -ngl 99 --parallel 4 --no-webui --jinja \
    --reasoning-budget 0 > logs/qwen-$1.log 2>&1 < /dev/null &
  echo $! > logs/qwen.pid
  for i in $(seq 120); do curl -sf http://127.0.0.1:$JUDGE_PORT/health > /dev/null && break; sleep 2; done
  curl -sf http://127.0.0.1:$JUDGE_PORT/health > /dev/null || { note "QWEN KO"; qwen_down; return 1; }
  python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/validate-$1-pre.json > logs/validate-$1-pre.log 2>&1
  local rc=$?; note "VALIDATION $1 avant rc=$rc"; [ $rc = 0 ] || { qwen_down; return 1; }
}
qwen_post() {
  python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/validate-$1-post.json > logs/validate-$1-post.log 2>&1
  note "VALIDATION $1 après rc=$?"
}
qwen_down() { [ -f logs/qwen.pid ] && kill $(cat logs/qwen.pid) && rm logs/qwen.pid; sleep 5; }

case ${1:-} in
  r1hf)  # poids HF de R1 v1.0 : P17 + 0,7 x delta SFT i1 + delta DPO i1 (recette rebuild_r1.sh de R2-C1)
    ad() { for s in 42 7 123 2024; do echo -n "$R/i1/$1-s$s/adapter "; done; }
    [ -f $W/r1-hf/model.safetensors ] || nice -n 19 $PY $C/merge_pref.py --base $R/base-p17 --out $W/r1-hf \
      --sft $(ad sft) --pref $(ad dpo) --sft-scale 0.7 > logs/r1hf.log 2>&1 || { note "R1-HF KO"; exit 1; }
    cp $R/base-p17/config.json $W/r1-hf/config.json
    note "R1-HF" ;;
  judge)  # passes A et B du juge A7 sur les sorties distinctes, paires Mask-DPO
    qwen_up corpus || exit 1
    for P in A B; do
      python3 $C/j.py $C/mask_pairs.py judge --pass $P --selected selected.jsonl --samples samples.jsonl \
        --cache judge/cache --threads 8 --max-missing 5 > logs/judge-$P.log 2>&1 || { note "JUGE $P KO"; qwen_down; exit 1; }
      note "JUGE $P $(tail -1 logs/judge-$P.log)"
    done
    qwen_post corpus
    qwen_down
    python3 $C/mask_pairs.py build --selected selected.jsonl --samples samples.jsonl --cache judge/cache --out pairs \
      > logs/pairs.log 2>&1 || { note "PAIRES KO"; exit 1; }
    note "PAIRES $(tail -1 logs/pairs.log)" ;;
  dpo)  # DPO masqué sur R1, graines 42 et 7, soupe, GGUF Q4_K_M
    V=$2; EP=${3:-1}
    for s in 42 7; do
      D=$V/dpo-s$s
      for try in 1 2 3 4 5 6 7 8; do
        [ -f $D/adapter/adapter_model.safetensors ] && break
        vram 2800
        nice -n 5 $PY $C/train_dpo.py --model $W/r1-hf --pairs pairs/pairs-train.jsonl --val-pairs pairs/pairs-val.jsonl \
          --val $R/mix-i1/val.jsonl --out $D --seed $s --lr ${LR:-2e-5} --beta 0.1 --epochs $EP --micro 2 \
          --mask-rejected > logs/$V-dpo-s$s.log 2>&1 && break
        note "DPO KO $V s$s essai $try"; sleep 120
      done
      [ -f $D/adapter/adapter_model.safetensors ] || { note "DPO ABANDON $V"; exit 1; }
      note "DPO $V s$s $(python3 -c "import json;d=json.load(open('$D/train_log.json'));print(d['steps'],d['vram_peak_mb'],d['evals'][0],d['evals'][-1])")"
    done
    G=gguf/r3t4-$V-Q4_K_M.gguf
    if [ ! -f $G ]; then
      disk 600  # fusion et f16 dans /dev/shm : seul le Q4_K_M (223 Mo) va sur /
      M=/dev/shm/r3t4-merged-$V
      nice -n 10 $PY $C/merge_pref.py --base $W/r1-hf --out $M --sft $V/dpo-s42/adapter $V/dpo-s7/adapter > logs/$V-merge.log 2>&1 \
        && cp $W/r1-hf/config.json $M/config.json \
        && nice -n 10 $PY /root/steph-ft/llama.cpp/convert_hf_to_gguf.py $M --outfile /dev/shm/r3t4-$V-f16.gguf --outtype f16 > logs/$V-conv.log 2>&1 \
        && $B/llama-quantize /dev/shm/r3t4-$V-f16.gguf $G Q4_K_M > logs/$V-q.log 2>&1 || { note "GGUF KO $V"; rm -rf $M /dev/shm/r3t4-$V-f16.gguf; exit 1; }
      rm -rf $M /dev/shm/r3t4-$V-f16.gguf
      note "GGUF $V $(sha256sum $G | cut -c1-16) $(stat -c %s $G)"
    fi ;;
  bench)  # banc v3 dev figé (0db04fa), graines 7, 42, 123
    for sd in 7 42 123; do
      OUT=runs/$3-dev-b$sd.json; [ -f $OUT ] && continue
      vram 1500
      python3 $C/bench_run.py --server $B/llama-server --model $2 --label $3-v3dev-b$sd --cases $C/dev.json --maxc 0 \
        --port 8976 --ngl 99 --payload "{\"seed\": $sd}" --out $OUT >> logs/bench-$3.log 2>&1 || note "BANC KO $3 b$sd"
    done
    note "BANC $3" ;;
  judgebench)  # une session : validation, runs, validation, fusion au format judge_v3
    OUT=$2; shift 2
    qwen_up $OUT || exit 1
    python3 $C/j.py $C/judge_bench_fast.py judge --harness $C/dev.json --cache judge/bench-cache --threads 8 "$@" \
      > logs/$OUT.log 2>&1 || note "JUGE BANC KO $OUT"
    qwen_post $OUT
    qwen_down
    python3 $C/judge_bench_fast.py merge --harness $C/dev.json --cache judge/bench-cache --out judge/$OUT.json "$@" \
      >> logs/$OUT.log 2>&1
    note "JUGE BANC $OUT $(tail -1 logs/$OUT.log)" ;;
  *) echo "usage : $0 r1hf | judge | dpo <variante> [époques] | bench <gguf> <nom> | judgebench <sortie> <run...>" >&2; exit 2 ;;
esac
