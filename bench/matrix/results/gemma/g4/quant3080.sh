#!/bin/bash
# G4 (reprise, A1000 injoignable depuis 17:06) : même chaîne sur l'hôte de la 3080.
#   QAT non quantifié -> GGUF bf16 (/dev/shm) -> imatrix sur les entrées publiques du banc v3 dev -> variantes à la demande,
#   au plus 3 GGUF sur le disque (18 Go libres) ; les couloirs effacent chaque GGUF après son run.
set -eu
W=/root/steph-ft/g4; B=$W/llama-b11205; L=$W/llama.cpp-b11205; Q=/dev/shm/g3-qat; PY=/root/steph-ft/venv/bin/python
BF=/dev/shm/g4-bf16.gguf
export PYTHONPATH=$L/gguf-py
cd $W
[ -f $BF ] || $PY $L/convert_hf_to_gguf.py $Q --outtype bf16 --outfile $BF > logs/convert.log 2>&1
[ -f calib/dev-prompts.txt ] || { mkdir -p calib; $PY calib.py dev.generic.json $Q calib/dev-prompts.txt > logs/calib.log 2>&1; }
[ -f imatrix.gguf ] || { while [ "$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)" -lt 8000 ]; do sleep 60; done
  /root/steph-ft/llama.cpp/build/bin/llama-imatrix -m $BF -f calib/dev-prompts.txt -o imatrix.gguf.tmp -c 1024 --chunks 96 -ngl 99 --parse-special > logs/imatrix.log 2>&1
  mv imatrix.gguf.tmp imatrix.gguf; }
sha256sum $BF imatrix.gguf calib/dev-prompts.txt > logs/sha-inputs.txt
while read -r m t opt; do
  [ -f gguf/$m.ok ] || [ -f runs/g4-$m-test-b7.json ] && continue
  while [ "$(ls gguf/*.gguf 2>/dev/null | wc -l)" -ge 3 ]; do sleep 30; done
  LD_LIBRARY_PATH=$B nice -n 5 $B/llama-quantize --imatrix imatrix.gguf $opt $BF gguf/$m.gguf.tmp $t 20 > logs/quant-$m.log 2>&1
  mv gguf/$m.gguf.tmp gguf/$m.gguf
  echo "$(sha256sum gguf/$m.gguf | cut -d' ' -f1) $(stat -c %s gguf/$m.gguf) $m" >> sha256-sizes.txt
  touch gguf/$m.ok; echo "$(date +%T) $m quantifié" >> logs/done.log
done <<'LIST'
q4_0 Q4_0
q4_0-ple3 Q4_0 --tensor-type per_layer_token_embd=q3_k
q4_k_m Q4_K_M
q4_0-ple4 Q4_0 --tensor-type per_layer_token_embd=q4_0
q3_k_m Q3_K_M
iq3_xxs IQ3_XXS
q4_0-ple2 Q4_0 --tensor-type per_layer_token_embd=q2_k
iq3_m IQ3_M
q2_k Q2_K
LIST
echo "$(date +%T) QUANT_DONE" >> logs/done.log
