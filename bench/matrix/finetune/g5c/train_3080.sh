#!/bin/bash
# G5c sur l'hôte de la 3080 (décision du 2026-10-01 : la 3060 reste à G3c) : mix G5c copié et audité par l'utilisateur
# dans /root/steph-ft/data/mix-g5c (sha256 vérifiés contre ceux de la 3060), recette a-sft de G5 à l'identique :
# run_k3.sh (SFT LoRA rang 16, lr 2e-4, 3 époques, graines 42 7 puis 123 2024 deux à deux, soupe uniforme, GGUF Q4_K_M)
# depuis P17 fusionné, comme `chain.sh sft a` et `soup a` de G5. Puis eval_3080.sh. Ollama arrêté au départ, relancé
# à la fin par ce script seulement s'il l'a arrêté.
set -u
K=/root/steph-ft/g5c; R=$K/repo; F=$R/bench/matrix/finetune; MIX=/root/steph-ft/data/mix-g5c; BASE=/root/steph-ft/r1/base-p17
SHA="9ee83dd2a9db89886cb90cf69728479a6fb8cbe302fd4a49c53b60faabd19b53 b1d7ada3836ab1db7a464e89188c6b97758f3cec9fbc38d2a6e324db4c8bb7aa"
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
cd $K; mkdir -p logs gguf
[ "$(sha256sum $MIX/train.jsonl $MIX/val.jsonl | cut -d' ' -f1 | paste -sd' ')" = "$SHA" ] || { note "ARRÊT : mix-g5c différent"; exit 1; }
until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge 7000 ]; do sleep 60; done
if systemctl is-active --quiet ollama; then systemctl stop ollama && touch $K/ollama.train.stopped && note "OLLAMA ARRÊTÉ (entraînement)"; fi
trap '[ -f $K/ollama.train.stopped ] && systemctl start ollama && rm $K/ollama.train.stopped && note "OLLAMA RELANCÉ"' EXIT
export PYTHONPATH=$R/src
k3() { K3=$K MIX=$MIX TAG=g5c SFT_LR=2e-4 F16_DIR=/tmp bash $F/pref/run_k3.sh $1 a $BASE; }
note "SFT départ (run_k3.sh, 4 graines deux à deux)"
k3 sft || { note "SFT KO"; exit 1; }
for s in 42 7 123 2024; do
  [ -f $K/a/sft-s$s/adapter/adapter_model.safetensors ] || { note "SFT KO s$s"; exit 1; }
  note "SFT s$s $(grep -v '^{' $K/logs/a-sft-s$s.log | grep 'meilleure' | tail -1 | cut -c1-120)"
done
k3 soup || { note "SOUPE KO"; exit 1; }
G=$K/gguf/g5c-a-sft-Q4_K_M.gguf
[ -f $G ] || { note "GGUF KO"; exit 1; }
note "GGUF g5c-a-sft $(sha256sum $G | cut -d' ' -f1) $(stat -c %s $G)"
bash $R/bench/matrix/finetune/g5c/eval_3080.sh
