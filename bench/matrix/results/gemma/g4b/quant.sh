#!/bin/bash
# G4b : G3b f16 -> Q4_0 sans imatrix, PLE (per_layer_token_embd) en Q3_K ; lancé par systemd-run -p AllowedCPUs=0-31 -p MemoryMax=32G sur xeon.
B=/root/steph-ft/llama/llama-b11205
cd /root/steph-ft/g3b
export LD_LIBRARY_PATH=$B:/root/steph-ft/vendor/lib
exec /usr/bin/nice -n 19 $B/llama-quantize --tensor-type per_layer_token_embd=q3_k gguf/g3b-f16.gguf g4b/g3b-off-ple3.gguf Q4_0 16
