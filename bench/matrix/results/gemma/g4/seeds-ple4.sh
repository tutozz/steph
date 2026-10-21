#!/bin/bash
# G4 : graines 42 et 123 pour off-ple4 (PLE en Q4_0, inventions égales à l'officiel en graine 7) ; bf16 reconverti dans /dev/shm puis effacé.
set -eu
W=/root/steph-ft/g4; B=$W/llama-b11205; L=$W/llama.cpp-b11205; BF=/dev/shm/g4-bf16.gguf
cd $W
systemctl stop ollama; echo "$(date +%T) ollama arrêté par G4 (graines off-ple4)" >> logs/done.log
[ -f $BF ] || PYTHONPATH=$L/gguf-py /root/steph-ft/venv/bin/python $L/convert_hf_to_gguf.py /dev/shm/g3-qat --outtype bf16 --outfile $BF > logs/convert-ple4.log 2>&1
touch gguf/off-ple4.keep
LD_LIBRARY_PATH=$B nice -n 5 $B/llama-quantize --tensor-type per_layer_token_embd=q4_0 $BF gguf/off-ple4.gguf.tmp Q4_0 20 > logs/quant-off-ple4-top.log 2>&1
mv gguf/off-ple4.gguf.tmp gguf/off-ple4.gguf; rm -f $BF
sha=$(sha256sum gguf/off-ple4.gguf | cut -d' ' -f1); grep -q "^$sha .* off-ple4$" sha256-sizes.txt && echo "$(date +%T) off-ple4 requantifié, sha256 identique" >> logs/done.log || echo "$(date +%T) off-ple4 SHA DIFFÉRENT $sha" >> logs/done.log
touch gguf/off-ple4.ok
printf "off-ple4 42\noff-ple4 123\n" > jobs.q
./lane.sh 8961 & ./lane.sh 8962 & wait
rm -f gguf/off-ple4.*
systemctl start ollama; echo "$(date +%T) ollama relancé par G4" >> logs/done.log
