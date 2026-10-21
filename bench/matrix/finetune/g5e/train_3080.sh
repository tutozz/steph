#!/bin/bash
# G5e sur l'hôte de la 3080 : recette a-sft de G5 à l'identique (train_3080.sh de G5d) sur mix-g5e (mix.sh) :
# run_k3.sh (SFT LoRA rang 16, lr 2e-4, 3 époques, graines 42 7 puis 123 2024 deux à deux, soupe uniforme, GGUF Q4_K_M)
# depuis P17 fusionné. Puis eval_3080.sh dev. Ollama arrêté au départ s'il tourne, relancé à la fin par ce script seulement
# s'il l'a arrêté. Carte partagée : attente de 7 Go libres.
set -u
K=/root/steph-ft/g5e; R=$K/repo; F=$R/bench/matrix/finetune; MIX=/root/steph-ft/data/mix-g5e; BASE=/root/steph-ft/r1/base-p17
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
cd $K; mkdir -p logs gguf
sha256sum --quiet -c <(grep mix-g5e $K/logs/mix-sha.txt) || { note "ARRÊT : mix-g5e différent de mix.sh"; exit 1; }
grep -q '"rejected": \[\]' $K/logs/leak-mix.log || { note "ARRÊT : cas du banc dans le mix"; exit 1; }
until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge 7000 ]; do sleep 60; done
if systemctl is-active --quiet ollama; then systemctl stop ollama && touch $K/ollama.train.stopped && note "OLLAMA ARRÊTÉ (entraînement)"; fi
trap '[ -f $K/ollama.train.stopped ] && systemctl start ollama && rm $K/ollama.train.stopped && note "OLLAMA RELANCÉ"' EXIT
export PYTHONPATH=$R/src
k3() { K3=$K MIX=$MIX TAG=g5e SFT_LR=2e-4 F16_DIR=/tmp bash $F/pref/run_k3.sh $1 a $BASE; }
note "SFT départ (run_k3.sh, 4 graines deux à deux)"
k3 sft || { note "SFT KO"; exit 1; }
for s in 42 7 123 2024; do
  [ -f $K/a/sft-s$s/adapter/adapter_model.safetensors ] || { note "SFT KO s$s"; exit 1; }
  note "SFT s$s $(grep -v '^{' $K/logs/a-sft-s$s.log | grep 'meilleure' | tail -1 | cut -c1-120)"
done
k3 soup || { note "SOUPE KO"; exit 1; }
G=$K/gguf/g5e-a-sft-Q4_K_M.gguf
[ -f $G ] || { note "GGUF KO"; exit 1; }
note "GGUF g5e-a-sft $(sha256sum $G | cut -d' ' -f1) $(stat -c %s $G)"
bash $F/g5e/eval_3080.sh dev
