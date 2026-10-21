#!/bin/bash
# R3-T2 partie 2 : juge A7 (Qwen3.5-9B Q4_K_M, sha256 03b74727…) sur une part des réponses du banc v3 dev, une part par
# carte libre. Session : validation 6/6 FR et EN avant, juge, validation après, arrêt du serveur lancé ici (par PID).
#   judge.sh <dossier> <llama-server> <qwen.gguf> <port> <part> <nparts> <run...>
# <dossier>/code porte j.py, judge_lib.py (A7 intact), judge_bench_fast.py, mask_pairs.py, judge_validate_v3.py,
# controls.json et dev.json (0db04fa) ; attend NEED Mo libres (8 000 par défaut) avant de lancer le serveur.
# Cache CACHE (judge/cache par défaut), fusionné ensuite sur le Mac (merge) ; un autre CACHE rejuge dans cette session
# des réponses déjà jugées ailleurs (contrôle d'accord entre sessions du juge). PARALLEL (8) : fentes du serveur ; à 2,
# 16 384 jetons par fente pour les contextes longs refusés à 8.
set -u
W=$1; SRV=$2; QWEN=$3; PORT=$4; PART=$5; NPARTS=$6; shift 6
C=$W/code; CACHE=${CACHE:-judge/cache}; cd $W; mkdir -p logs $CACHE
export JUDGE_PORT=$PORT PYTHONPATH=$C
note() { echo "$(date +%H:%M) $*" >> $W/run.done; }
down() { [ -f logs/qwen-$PART.pid ] && kill $(cat logs/qwen-$PART.pid); rm -f logs/qwen-$PART.pid; sleep 5; }

note "ATTENTE ${NEED:-8000} Mo libres, part $PART"
until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)" -ge ${NEED:-8000} ]; do sleep 60; done
nice -n 19 $SRV -m $QWEN --host 127.0.0.1 --port $PORT -c 32768 -ngl 99 --parallel ${PARALLEL:-8} --no-webui --jinja \
  --reasoning-budget 0 > logs/qwen-$PART.log 2>&1 < /dev/null &
echo $! > logs/qwen-$PART.pid
for i in $(seq 180); do curl -sf http://127.0.0.1:$PORT/health > /dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:$PORT/health > /dev/null || { note "QWEN KO part $PART"; down; exit 1; }
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/validate-$PART-pre.json > logs/validate-$PART-pre.log 2>&1
rc=$?; note "VALIDATION part $PART avant rc=$rc"; [ $rc = 0 ] || { down; exit 1; }
nice -n 19 python3 $C/j.py $C/judge_bench_fast.py judge --harness $C/dev.json --cache $CACHE --shard $PART \
  --nshards $NPARTS --threads 8 "$@" > logs/judge-$PART.log 2>&1 || note "JUGE KO part $PART"
python3 $C/j.py $C/judge_validate_v3.py run $C/controls.json judge/validate-$PART-post.json > logs/validate-$PART-post.log 2>&1
note "VALIDATION part $PART après rc=$?"
down
note "JUGE part $PART $(tail -1 logs/judge-$PART.log)"
