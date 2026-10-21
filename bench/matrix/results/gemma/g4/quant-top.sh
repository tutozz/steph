#!/bin/bash
# G4, 3 graines pour les 2 meilleures (off-ple2, off-ple3) : même quantification que quant-off.sh (déterministe, sha256 comparé),
#   GGUF gardés (.keep) jusqu'à la fin des graines 42 et 123 ; au plus 2 GGUF sur le disque.
set -eu
W=/root/steph-ft/g4; B=$W/llama-b11205; BF=/dev/shm/g4-bf16.gguf
cd $W
while read -r m t opt; do
  while [ "$(ls gguf/*.gguf 2>/dev/null | wc -l)" -ge 2 ] || [ "$(df --output=avail -B1G / | tail -1)" -lt 6 ]; do sleep 30; done
  touch gguf/$m.keep
  LD_LIBRARY_PATH=$B nice -n 5 $B/llama-quantize $opt $BF gguf/$m.gguf.tmp $t 20 > logs/quant-$m-top.log 2>&1
  mv gguf/$m.gguf.tmp gguf/$m.gguf
  sha=$(sha256sum gguf/$m.gguf | cut -d' ' -f1); grep -q "^$sha .* $m$" sha256-sizes.txt && echo "$(date +%T) $m requantifié, sha256 identique" >> logs/done.log || echo "$(date +%T) $m requantifié, SHA DIFFÉRENT $sha" >> logs/done.log
  touch gguf/$m.ok
done <<'LIST'
off-ple2 Q4_0 --tensor-type per_layer_token_embd=q2_k
off-ple3 Q4_0 --tensor-type per_layer_token_embd=q3_k
LIST
