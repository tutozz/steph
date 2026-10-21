#!/bin/bash
# G4, deuxième vague : couches Q4_0 sans imatrix (= Q4_0 officiel QAT, reproduit à l'identique en G3 fondation)
#   et seul le PLE (per_layer_token_embd, lu par index) descendu ; au plus 2 GGUF sur le disque (8 Go libres).
set -eu
W=/root/steph-ft/g4; B=$W/llama-b11205; BF=/dev/shm/g4-bf16.gguf
cd $W
while read -r m t opt; do
  [ -f gguf/$m.ok ] || [ -f runs/g4-$m-test-b7.json ] && continue
  while [ "$(ls gguf/*.gguf 2>/dev/null | wc -l)" -ge 2 ] || [ "$(df --output=avail -B1G / | tail -1)" -lt 6 ]; do sleep 30; done
  LD_LIBRARY_PATH=$B nice -n 5 $B/llama-quantize $opt $BF gguf/$m.gguf.tmp $t 20 > logs/quant-$m.log 2>&1
  mv gguf/$m.gguf.tmp gguf/$m.gguf
  echo "$(sha256sum gguf/$m.gguf | cut -d' ' -f1) $(stat -c %s gguf/$m.gguf) $m" >> sha256-sizes.txt
  touch gguf/$m.ok; echo "$(date +%T) $m quantifié" >> logs/done.log
done <<'LIST'
off-ple3 Q4_0 --tensor-type per_layer_token_embd=q3_k
off-ple2 Q4_0 --tensor-type per_layer_token_embd=q2_k
off-ple4 Q4_0 --tensor-type per_layer_token_embd=q4_0
LIST
