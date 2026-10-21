#!/bin/bash
# G5 : enchaînement sur l'hôte de la 3080. Arrête Ollama au départ (relancé par close.sh), attend une carte libre.
#   variante a : recette R1 SFT sur final-x4-l5 + correctif de langue ; a-l07 : + DPO questions à réponse présente
#   variante b : a, mais étiquettes remplacées par les sorties de G3b jugées ok (distillation par séquences)
set -u
K=/root/steph-ft/g5; C="bash $K/repo/bench/matrix/finetune/g5/chain.sh"
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
# un banc d'un autre agent (G4b, 1,8 Go) partage la carte : SFT une graine à la fois, bancs à la suite
export SFT_PAIRS="42 7 123 2024"
until [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)" -ge 5000 ]; do sleep 60; done
if systemctl is-active --quiet ollama; then systemctl stop ollama && touch $K/ollama.stopped && note "OLLAMA ARRÊTÉ"; fi
note "DÉPART"
$C l5 && $C langfix && $C mix || exit 1
$C sft a $K/mix && $C soup a $K/mix || exit 1
$C qapairs a $K/mix && $C dpo a $K/mix || exit 1
$C bench v10 /root/steph-ft/r1/gguf/steph-speak-granite-4.0-h-350M-dpo-v1.0-Q4_K_M.gguf dev
$C bench a-sft $K/gguf/g5-a-sft-Q4_K_M.gguf dev
$C bench a-l07 $K/gguf/g5-a-l07-Q4_K_M.gguf dev
$C teacher && $C distill || exit 1
$C sft b $K/mix-distill && $C soup b $K/mix-distill || exit 1
$C bench b-sft $K/gguf/g5-b-sft-Q4_K_M.gguf dev
note "DRIVE FIN"
