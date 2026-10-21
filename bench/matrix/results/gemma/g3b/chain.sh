#!/bin/bash
# G3b (copie de g3/chain.sh, W=g3b) : adaptateurs LoRA (soupe uniforme [+ DPO]) -> fusion bf16 -> GGUF f16 -> Q4_0 sans imatrix (même quantification que le Q4_0 officiel QAT).
#   chain.sh <nom> <adaptateur>... [--add <adaptateur DPO>]
set -eu
G=/root/steph-ft/gemma; W=/root/steph-ft/g3b; L=$G/llama.cpp-b11205; B=/root/steph-ft/llama/llama-b11205; F=$W/repo/bench/matrix/finetune/gemma
export PYTHONPATH=$L/gguf-py:$W/repo/src LD_LIBRARY_PATH=$B:/root/steph-ft/vendor/lib
PY=/root/steph-ft/venv/bin/python; Q=$G/gemma-4-E2B-it-qat-q4_0-unquantized
N=$1; shift; AD=(); ADD=()
while [ $# -gt 0 ]; do if [ "$1" = --add ]; then ADD+=("$2"); shift 2; else AD+=("$1"); shift; fi; done
mkdir -p $W/gguf; cd $W
[ -f gguf/$N-f16.gguf ] || { $PY $F/merge_gemma.py --model $Q --adapters "${AD[@]}" ${ADD:+--add "${ADD[@]}"} --out /dev/shm/g3b-merged-$N > logs/merge-$N.log 2>&1
  $PY $L/convert_hf_to_gguf.py /dev/shm/g3b-merged-$N --outtype f16 --outfile gguf/$N-f16.gguf > logs/convert-$N.log 2>&1; rm -rf /dev/shm/g3b-merged-$N; }
[ -f gguf/$N-Q4_0.gguf ] || $B/llama-quantize gguf/$N-f16.gguf gguf/$N-Q4_0.gguf Q4_0 16 > logs/quant-$N.log 2>&1
sha256sum gguf/$N-f16.gguf gguf/$N-Q4_0.gguf | tee logs/sha-$N.txt
stat -c "%n %s" gguf/$N-f16.gguf gguf/$N-Q4_0.gguf
