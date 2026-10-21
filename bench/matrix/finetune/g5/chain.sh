#!/bin/bash
# G5 : petit modèle des PC lents, Granite 4.0 H 350M depuis P17 fusionné (base de v1.0), sur l'hôte de la 3080
# (corpus brut, final-x4, mix-extra de R1, 71 paires P17 : tout ce que demande la recette R1 est sur place).
#   chain.sh l5 | langfix | mix               données (corpus : rien ne quitte l'hôte)
#   chain.sh sft <v> <mix> | soup <v> <mix>   recette R1 (run_k3.sh) : SFT 4 graines, soupe uniforme, GGUF g5-<v>-sft
#   chain.sh qapairs <v> <mix> | dpo <v> <mix> DPO sur les seules questions à réponse présente, fusion SFT 0,7 (v1.0)
#   chain.sh teacher | distill                sorties de G3b (prompt générique) jugées A7, puis mix distillé
#   chain.sh bench <label> <gguf> <dev|test> [graines]
# Tout sous nice ; une étape faite est sautée ; journal : run.done.
set -u
STEP=$1; shift
K=/root/steph-ft/g5; R=$K/repo; F=$R/bench/matrix/finetune; G=$F/g5; D=/root/steph-ft/data
PY=/root/steph-ft/venv/bin/python; B=/root/steph-ft/llama.cpp/build/bin; CONV=/root/steph-ft/llama.cpp/convert_hf_to_gguf.py
QWEN=/root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf; BASE=/root/steph-ft/r1/base-p17; J=$K/judge
TEACHER=/dev/shm/g5-g3b-Q4_0.gguf; TSHA=e7ca421b0640d2aea4334f3273064d01c0a4764d8b6390ad434be6480a13ae74
export PYTHONPATH=$R/src HF_HOME=/root/steph-ft/hf-cache HF_HUB_OFFLINE=1
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
cd $K

serve() {  # gguf port contexte slots -> PID dans server-<port>.pid
  nice -n 5 $B/llama-server -m $1 --host 127.0.0.1 --port $2 -c $3 -ngl 99 --parallel $4 --no-webui --jinja --reasoning-budget 0 \
    > $K/logs/server-$2.log 2>&1 < /dev/null &
  echo $! > $K/server-$2.pid
  for i in $(seq 150); do curl -sf http://127.0.0.1:$2/health >/dev/null && return 0; sleep 2; done
  return 1
}
wait_free() {  # Mo libres attendus sur la carte (un juge ou un banc d'un autre agent la partage)
  until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge $1 ]; do sleep 60; done
}
unserve() { [ -f $K/server-$1.pid ] && kill $(cat $K/server-$1.pid) && rm $K/server-$1.pid; sleep 5; }
validate() {  # contrôles A7 6/6 FR et EN du juge du port 8931
  (cd $J && JUDGE_PORT=8931 PYTHONPATH=$J/jl:$R/bench/matrix/v3/tools python3 j.py $R/bench/matrix/v3/tools/judge_validate_v3.py run \
    controls.json $K/logs/validate-$1.json > $K/logs/validate-$1.log 2>&1); note "VALIDATION $1 rc=$? $(tail -1 $K/logs/validate-$1.log)"
}
judge_gen() {  # dossier de données, gen.jsonl, verdicts.jsonl (juge 9B servi par l'appelant sur 8931)
  PYTHONPATH=$J/jl:$F/pref nice -n 5 python3 $F/pref/judge_outputs.py --data $1 --gen $2 --out $3 --parallel 8 > $3.log 2>&1
}
gguf() {  # dossier HF fusionné, nom
  cp -L $BASE/config.json $1/config.json
  nice -n 5 $PY $CONV $1 --outfile /tmp/$2-f16.gguf --outtype f16 > $K/logs/$2-conv.log 2>&1 \
    && nice -n 5 $B/llama-quantize /tmp/$2-f16.gguf $K/gguf/$2-Q4_K_M.gguf Q4_K_M > $K/logs/$2-q.log 2>&1 || { note "GGUF KO $2"; return 1; }
  rm -rf $1 /tmp/$2-f16.gguf
  note "GGUF $2 $(sha256sum $K/gguf/$2-Q4_K_M.gguf | cut -c1-16) $(stat -c %s $K/gguf/$2-Q4_K_M.gguf)"
}
k3() { K3=$K MIX=$1 TAG=g5 SFT_LR=2e-4 bash $F/pref/run_k3.sh $2 $3 $BASE; }

case $STEP in
  l5)  # bloc de faits L5 dans les entrées de résumé (x4_l5_inputs.py), sur la machine du corpus
    [ -f $D/final-x4-l5/SHA256SUMS ] && exit 0
    nice -n 5 python3 $F/x4_l5_inputs.py --final $D/final-x4 --raw $D/corpus/*.jsonl $D/snapshot-1/clean/*.jsonl \
      --out $D/final-x4-l5 > $K/logs/l5.json 2> $K/logs/l5.err && note "L5 $(wc -l < $D/final-x4-l5/SHA256SUMS) fichiers" ;;
  langfix)  # correctif de langue de G3b (g3b_langfix.py), enseignant et juge A7 9B
    L=$K/langfix; mkdir -p $L/judge
    [ -f $L/langfix.jsonl ] && exit 0
    [ -f $L/subset.jsonl ] || python3 $F/gemma/g3b_langfix.py select --raw $D/corpus/linux-dev.jsonl $D/corpus/linux-low.jsonl \
      $D/corpus/macos.jsonl $D/snapshot-1/clean/*.jsonl --n 500 --seed 42 --out $L/subset.jsonl > $K/logs/lf-select.log && note "LANGUE choix $(cat $K/logs/lf-select.log)"
    wait_free 7000; serve $QWEN 8931 16384 4 || { note "JUGE KO langfix"; exit 1; }
    validate lf-pre
    nice -n 5 python3 $F/gemma/g3b_langfix.py label --in $L/subset.jsonl --port 8931 --parallel 4 --out $L/labeled.jsonl > $K/logs/lf-label.log 2>&1
    note "LANGUE étiquettes rc=$? $(tail -1 $K/logs/lf-label.log)"
    python3 $F/gemma/g3b_langfix.py rows --labeled $L/labeled.jsonl --out $L/cand.jsonl > $K/logs/lf-rows.log && note "LANGUE $(cat $K/logs/lf-rows.log)"
    (cd $L && JUDGE_PORT=8931 PYTHONPATH=$J/jl python3 $J/j.py $F/judge_corpus_2pass.py cand.jsonl langfix judge > $K/logs/lf-judge.log 2>&1)
    note "LANGUE juge rc=$? $(tail -1 $K/logs/lf-judge.log)"
    validate lf-post
    unserve 8931
    python3 $F/gemma/g3b_langfix.py keep --cand $L/cand.jsonl --verdicts $L/judge/verdicts-langfix.jsonl --n 300 --seed 42 \
      --out $L/langfix.jsonl > $K/logs/lf-keep.log && note "LANGUE gardées $(cat $K/logs/lf-keep.log)" ;;
  mix)  # chaîne R1 de r3_t2_x4/build_mix.sh sur final-x4-l5, mix-extra de R1, contamination par ligne, correctif x2
    [ -f $K/mix/train.jsonl ] && exit 0
    X=$K/x4; mkdir -p $X $K/clean $K/mix
    ( cd $D && cat final-x4-l5/macos.jsonl final-x4-l5/linux-low.jsonl final-x4-l5/linux-dev.jsonl final-x4-l5/snapshot-linux-dev.jsonl \
        final-x4-l5/snapshot-linux-low.jsonl > $X/fr.jsonl
      nice -n 5 python3 $F/fix_labels.py $X/fr.jsonl $X/fr.fixed.jsonl
      nice -n 5 python3 $F/compose_train.py $X/fr.fixed.jsonl $X/fr-mix --cap 250 --bench $R/bench/matrix/cases.json
      nice -n 5 python3 $F/compose_k3.py --fr-mix $X/fr-mix --fr-raw corpus/*.jsonl snapshot-1/clean/*.jsonl \
        --en final-x4-l5/macos.en.jsonl final-x4-l5/linux-low.en.jsonl --en-raw corpus/*.en.jsonl \
        --feature detail=final-x4-l5/detail.jsonl --feature start=final/start.jsonl --feature progress=final-x4-l5/progress.jsonl \
        --feature flux=final-x4-l5/flux.jsonl --feature summary_residual=final/summary_residual.jsonl --feature-raw corpus/features-*.jsonl \
        --qa final/qa_train.jsonl --bench $R/bench/matrix/cases.json --speak-bench $R/benchmark/data/v1 --max-chars 587 \
        --out $X/k3mix > $K/logs/k3mix.json
      nice -n 5 python3 $F/compose_r1.py --base $X/k3mix --extra /root/steph-ft/r1/mix-extra --repeat en_summary=2 --keep detail=0.5 \
        --out $K/mix-x4r1-l5 > $K/logs/mix-x4r1-l5.json ) || { note "MIX KO"; exit 1; }
    python3 $R/bench/matrix/v3/tools/leak_check.py prints $K/v3prints-head.json $R/bench/matrix/v3/cases/*.jsonl \
      $R/bench/matrix/v3/cases/dev/*.jsonl $R/bench/matrix/v3/cases/test/*.jsonl > /dev/null
    for f in langfix/langfix mix-x4r1-l5/train mix-x4r1-l5/val; do
      n=$(echo $f | tr / -)
      python3 $R/bench/matrix/v3/tools/leak_check.py drop $K/v3prints-head.json $K/$f.jsonl $K/clean/$n.jsonl > $K/logs/drop-$n.log
      note "SANS FUITE $f $(cut -c1-120 $K/logs/drop-$n.log)"
    done
    cat $K/clean/mix-x4r1-l5-train.jsonl $K/clean/langfix-langfix.jsonl $K/clean/langfix-langfix.jsonl > $K/mix/train.jsonl
    cp $K/clean/mix-x4r1-l5-val.jsonl $K/mix/val.jsonl
    python3 $R/bench/matrix/v3/tools/leak_check.py scan $K/v3prints-head.json $K/logs/leak-mix.json $K/mix/train.jsonl $K/mix/val.jsonl \
      > $K/logs/leak-mix.log 2>&1
    sha256sum $K/mix-x4r1-l5/*.jsonl $K/mix/*.jsonl $K/langfix/langfix.jsonl > $K/logs/mix-sha.txt
    rm -rf $X; note "MIX $(wc -l < $K/mix/train.jsonl) / $(wc -l < $K/mix/val.jsonl) ; fuite $(tail -1 $K/logs/leak-mix.log | cut -c1-80)" ;;
  sft)  # $1 variante, $2 mix
    grep -q '"rejected": \[\]' $K/logs/leak-$1.log 2>/dev/null || grep -q '"rejected": \[\]' $K/logs/leak-mix.log || { note "ARRÊT : cas du banc dans le mix"; exit 1; }
    k3 $2 sft $1 ;;
  soup) k3 $2 soup $1 ;;
  qapairs)  # $1 variante, $2 mix : sorties de la soupe SFT sur les questions à réponse présente, juge A7, paires
    W=$K/$1; [ -f $W/pairs-counts.json ] && exit 0
    python3 $G/g5_data.py qa-present --data $2 --out $W/qa > $K/logs/$1-qa-present.log && note "QUESTIONS PRÉSENTES $1 $(cat $K/logs/$1-qa-present.log)"
    serve $K/gguf/g5-$1-sft-Q4_K_M.gguf 8950 16384 8 || { note "SERVEUR SFT KO $1"; exit 1; }
    nice -n 5 python3 $F/pref/gen_outputs.py --data $W/qa --port 8950 --out $W/qa-gen.jsonl --seeds 42 7 123 --repeat-penalty 1.0 \
      --max-tokens 160 --parallel 8 > $K/logs/$1-qa-gen.log 2>&1
    unserve 8950
    wait_free 7000; serve $QWEN 8931 16384 4 || { note "JUGE KO $1"; exit 1; }
    judge_gen $W/qa $W/qa-gen.jsonl $W/qa-verdicts.jsonl || { note "JUGE KO $1"; unserve 8931; exit 1; }
    unserve 8931
    python3 $G/g5_data.py pairs --data $W/qa --gen $W/qa-gen.jsonl --verdicts $W/qa-verdicts.jsonl --out $W > $K/logs/$1-pairs.log \
      && note "PAIRES $1 $(tr -d '\n ' < $W/pairs-counts.json)" ;;
  dpo)  # $1 variante, $2 mix : DPO 4 graines de run_k3.sh (60 pas, 12 époques au plus), sans les paires P17, fusion SFT 0,7
    W=$K/$1; cd $W; N=g5-$1-l07; SEEDS="42 7 123 2024"
    n=$(wc -l < pairs-train.jsonl); SPE=$(( (n + 15) / 16 )); EP=$(python3 -c "print(round(min(12.0, 60 / $SPE), 2))")
    note "DPO $1 : $n paires, $EP époques"
    ad() { for s in $SEEDS; do echo -n "$W/$1-s$s/adapter "; done; }
    for s in $SEEDS; do
      [ -f dpo-s$s/adapter/adapter_model.safetensors ] || nice -n 5 $PY $F/pref/train_dpo.py --model $BASE --sft-adapters $(ad sft) \
        --pairs pairs-train.jsonl --val-pairs pairs-val.jsonl --val $2/val.jsonl --out dpo-s$s --seed $s --lr 2e-5 --epochs $EP \
        > $K/logs/$1-dpo-s$s.log 2>&1 || { note "DPO KO $1 s$s"; exit 1; }
    done
    [ -f $K/gguf/$N-Q4_K_M.gguf ] || { nice -n 5 $PY $F/pref/merge_pref.py --base $BASE --out $W/merged-l07 --sft $(ad sft) \
      --pref $(ad dpo) --sft-scale 0.7 > $K/logs/$N-merge.log 2>&1 || { note "FUSION KO $N"; exit 1; }
      gguf $W/merged-l07 $N; } ;;
  teacher)  # G3b (GGUF e7ca421b) sur les entrées du mix au prompt générique de production, glouton, puis juge A7
    T=$K/teacher; mkdir -p $T
    [ -f $T/verdicts.jsonl.done ] && exit 0
    [ "$(sha256sum $TEACHER | cut -d' ' -f1)" = $TSHA ] || { note "ENSEIGNANT absent ou différent"; exit 1; }
    python3 $G/g5_data.py generic --data $K/mix --out $T/generic > $K/logs/teacher-generic.log && note "GÉNÉRIQUE $(cat $K/logs/teacher-generic.log)"
    wait_free 6000; serve $TEACHER 8951 32768 8 || { note "SERVEUR G3b KO"; exit 1; }
    nice -n 5 python3 $F/pref/gen_outputs.py --data $T/generic --port 8951 --out $T/gen.jsonl --seeds 42 --temperature 0.0 \
      --repeat-penalty 1.0 --max-tokens 300 --parallel 8 > $K/logs/teacher-gen.log 2>&1
    note "ENSEIGNANT sorties $(wc -l < $T/gen.jsonl) $(grep -c erreur $K/logs/teacher-gen.log)"
    unserve 8951
    wait_free 7000; serve $QWEN 8931 16384 4 || { note "JUGE KO enseignant"; exit 1; }
    validate teacher-pre
    judge_gen $T/generic $T/gen.jsonl $T/verdicts.jsonl || { note "JUGE KO enseignant"; unserve 8931; exit 1; }
    validate teacher-post
    unserve 8931; touch $T/verdicts.jsonl.done; note "ENSEIGNANT jugé $(tail -1 $T/verdicts.jsonl.log | cut -c1-120)" ;;
  distill)
    [ -f $K/mix-distill/train.jsonl ] && exit 0
    python3 $G/g5_data.py distill --data $K/mix --gen $K/teacher/gen.jsonl --verdicts $K/teacher/verdicts.jsonl --out $K/mix-distill \
      > $K/logs/distill.log && note "DISTILLATION $(cat $K/logs/distill.log)"
    python3 $R/bench/matrix/v3/tools/leak_check.py scan $K/v3prints-head.json $K/logs/leak-mix-distill.json $K/mix-distill/train.jsonl \
      $K/mix-distill/val.jsonl > $K/logs/leak-b.log 2>&1; note "FUITE distill $(tail -1 $K/logs/leak-b.log | cut -c1-80)"
    sha256sum $K/mix-distill/*.jsonl >> $K/logs/mix-sha.txt ;;
  bench)  # $1 label, $2 gguf, $3 dev|test, graines
    L=$1; M=$2; S=$3; shift 3; mkdir -p $K/runs
    echo "$L $(sha256sum $M)" >> $K/gguf-sha256.txt
    for sd in ${@:-7 42 123}; do
      O=$K/runs/$L-$S-b$sd.json
      [ -f $O ] || nice -n 5 python3 $R/bench/matrix/bench_run.py --server $B/llama-server --model $M --label g5-$L-v3$S-b$sd \
        --cases $R/bench/matrix/v3/harness/$S.json --maxc 0 --port 897${sd: -1} --ngl 99 --abort-ttft 120 \
        --payload "{\"seed\": $sd}" --out $O >> $K/logs/bench-$L.log 2>&1
      note "BANC $L $S b$sd rc=$?"
    done ;;
  *) echo "usage : voir l'en-tête" >&2; exit 2 ;;
esac
