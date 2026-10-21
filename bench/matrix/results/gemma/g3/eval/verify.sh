#!/bin/bash
# Attend chaque GGUF copié, vérifie son sha256 attendu, puis le rend visible aux couloirs.
cd /root/steph-ft/g3/eval/gguf
check() { # <fichier> <étiquette> <sha256>
  until [ "$(sha256sum $1 2>/dev/null | cut -d" " -f1)" = "$3" ]; do sleep 60; done
  ln -sf $1 $2.gguf && touch $2.ok && echo "$(date +%T) $2 sha256 ok" >> ../logs/done.log
}
check dpo-s42-Q4_0.gguf dpo-s42 3bb6e19c372f5380c0ad08f4a78b77a6a294ed157140bbe4880251c7d951888e &
check gemma-raw-Q4_0.gguf gemma-raw fa401b55b07ee70a54c6dae3903c783a6e65064312529ea57175cb5f8dec6634 &
check granite41-3b-Q4_K_M.gguf granite41-3b 102aba5b4bd85bca2570e4ea857d699c360cae5ae03abb2f0f945090709f05a1 &
wait
