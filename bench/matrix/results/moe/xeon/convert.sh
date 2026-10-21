#!/bin/bash
# G6 : conversion en GGUF (llama.cpp b11205, convert_hf_to_gguf.py) puis Q4_K_M, pour les MoE sans GGUF officiel.
set -eu
D=/root/steph-ft/g6; cd $D; export LD_LIBRARY_PATH=/root/steph-ft/vendor/lib
for n in EuroMoE-2.6B-A0.6B-Instruct-2512 Marco-Nano-Instruct; do
  [ -f models/$n-Q4_K_M.gguf ] && continue
  PYTHONPATH=$D/llama.cpp/gguf-py /root/steph-ft/venv/bin/python llama.cpp/convert_hf_to_gguf.py hf/$n --outtype bf16 --outfile hf/$n-bf16.gguf
  /root/steph-ft/llama/llama-b11205/llama-quantize hf/$n-bf16.gguf models/$n-Q4_K_M.gguf Q4_K_M 8
  rm -f hf/$n-bf16.gguf
  sha256sum models/$n-Q4_K_M.gguf
done
echo CONVDONE
