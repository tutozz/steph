#!/bin/bash
# R3-T2 partie 3 : dense x4 (partie 2) et dense R2-T1 (ancien corpus) passés dans les mêmes couloirs que R1 (lane.sh,
# ports 8971-8973), après le banc dev Granite H du pilote p3_driver.sh ; même carte, même build, même dev.json figé.
set -u
D=/root/steph-ft/loop/r3t2p3; G=/root/steph-ft/loop/r3t2p2/gguf/r3p2-dense-x4-l10-Q4_K_M.gguf
note() { echo "$(date +%H:%M) $*" >> $D/run.done; }
note "DENSE ATTENTE GGUF et fin du banc Granite H"
until [ -f $G ] && grep -q "DEV FAIT" $D/run.done; do sleep 60; done
ln -sf $G $D/gguf/dense-x4-Q4_K_M.gguf
ln -sf /root/steph-ft/loop/r2t1/gguf/r2t1-dpo-l10-Q4_K_M.gguf $D/gguf/r2t1-dense-Q4_K_M.gguf
for g in $D/gguf/dense-x4-Q4_K_M.gguf $D/gguf/r2t1-dense-Q4_K_M.gguf; do
  echo "$(sha256sum < $(readlink -f $g) | cut -c1-64) $(ls -lL $g | awk '{print $5}') $(basename $g)"; done >> $D/gguf-sha256.txt
for p in 8971:7 8972:42 8973:123; do
  bash $D/lane.sh ${p%%:*} ${p##*:} dense-x4 r2t1-dense &
done
wait
note "DENSE DEV FAIT"
