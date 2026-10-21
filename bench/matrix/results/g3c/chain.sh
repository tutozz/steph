#!/bin/bash
# G3c (copie de g3b/chain.sh, W=g3c/ft) sur xeon : adaptateur LoRA -> fusion bf16 -> GGUF f16 -> Q4_0 sans imatrix
# (quantification du Q4_0 officiel QAT) -> variante off-ple3 (G4b : per_layer_token_embd en q3_k, le reste en Q4_0).
#   chain.sh <nom> <adaptateur>
set -eu
G=/root/steph-ft/gemma; W=/root/steph-ft/g3c/ft; L=$G/llama.cpp-b11205; B=/root/steph-ft/llama/llama-b11205
F=/root/steph-ft/g3b/repo/bench/matrix/finetune/gemma
export PYTHONPATH=$L/gguf-py:/root/steph-ft/g3b/repo/src LD_LIBRARY_PATH=$B:/root/steph-ft/vendor/lib
PY=/root/steph-ft/venv/bin/python; Q=$G/gemma-4-E2B-it-qat-q4_0-unquantized
N=$1; AD=$2
mkdir -p $W/gguf $W/logs; cd $W
[ -f gguf/$N-f16.gguf ] || { nice -n 19 $PY $F/merge_gemma.py --model $Q --adapters $AD --out /dev/shm/g3c-merged-$N > logs/merge-$N.log 2>&1
  nice -n 19 $PY $L/convert_hf_to_gguf.py /dev/shm/g3c-merged-$N --outtype f16 --outfile gguf/$N-f16.gguf > logs/convert-$N.log 2>&1
  rm -rf /dev/shm/g3c-merged-$N; }
[ -f gguf/$N-Q4_0.gguf ] || nice -n 19 $B/llama-quantize gguf/$N-f16.gguf gguf/$N-Q4_0.gguf Q4_0 16 > logs/quant-$N.log 2>&1
[ -f gguf/$N-off-ple3.gguf ] || nice -n 19 $B/llama-quantize --tensor-type per_layer_token_embd=q3_k gguf/$N-f16.gguf \
  gguf/$N-off-ple3.gguf Q4_0 16 > logs/quant-$N-off-ple3.log 2>&1
sha256sum gguf/$N-f16.gguf gguf/$N-Q4_0.gguf gguf/$N-off-ple3.gguf | tee logs/sha-$N.txt
stat -c "%n %s" gguf/$N-f16.gguf gguf/$N-Q4_0.gguf gguf/$N-off-ple3.gguf
