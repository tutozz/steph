#!/bin/bash
# G4 : QAT non quantifié -> GGUF bf16 -> imatrix (entrées publiques du banc v3 dev) -> variantes ; KL contre le bf16 sur les docs (jamais vus par l'imatrix).
set -eu
W=/root/steph-ft/g4; B=/root/steph-ft/llama/cpu; L=$W/llama.cpp-b11205; Q=/root/steph-ft/gemma/qat; PY=/root/steph-ft/venv/bin/python
export LD_LIBRARY_PATH=$B PYTHONPATH=$L/gguf-py
cd $W
[ -f gguf/bf16.gguf ] || $PY $L/convert_hf_to_gguf.py $Q --outtype bf16 --outfile gguf/bf16.gguf > logs/convert.log 2>&1
[ -f calib/dev-prompts.txt ] || $PY calib.py dev.generic.json $Q calib/dev-prompts.txt > logs/calib.log 2>&1
[ -f gguf/imatrix.gguf ] || $B/llama-imatrix -m gguf/bf16.gguf -f calib/dev-prompts.txt -o gguf/imatrix.gguf -c 1024 --chunks 96 -t 24 $IMX_SPECIAL > logs/imatrix.log 2>&1
q() { # <nom> <type> [options]
  local n=$1 t=$2; shift 2
  [ -f gguf/$n.gguf ] || $B/llama-quantize --imatrix gguf/imatrix.gguf "$@" gguf/bf16.gguf gguf/$n.gguf $t 24 > logs/quant-$n.log 2>&1
}
q q4_0 Q4_0
q q4_k_m Q4_K_M
q q3_k_m Q3_K_M
q iq3_m IQ3_M
q iq3_xxs IQ3_XXS
q q2_k Q2_K
q q4_0-ple4 Q4_0 --tensor-type per_layer_token_embd=q4_0
q q4_0-ple3 Q4_0 --tensor-type per_layer_token_embd=q3_k
q q4_0-ple2 Q4_0 --tensor-type per_layer_token_embd=q2_k
echo QUANT_DONE >> logs/done.log
T="-t 24 -c 512 --chunks 40 -f kld-text.txt"
[ -f kld/base.kld ] || $B/llama-perplexity -m gguf/bf16.gguf $T --kl-divergence-base kld/base.kld > logs/kld-bf16.log 2>&1
for m in official q4_0 q4_k_m q3_k_m iq3_m iq3_xxs q2_k q4_0-ple4 q4_0-ple3 q4_0-ple2; do
  f=gguf/$m.gguf; [ $m = official ] && f=/root/steph-ft/loop/x3/raw/gemma-4-E2B_q4_0-it.gguf
  [ -f logs/kld-$m.log ] || $B/llama-perplexity -m $f $T --kl-divergence-base kld/base.kld --kl-divergence > logs/kld-$m.log 2>&1
done
sha256sum gguf/*.gguf > sha256.txt; stat -c "%n %s" gguf/*.gguf > sizes.txt
echo KLD_DONE >> logs/done.log
