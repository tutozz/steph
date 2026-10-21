#!/bin/bash
# G5e : mélange de G5d (mix-g5d, 18bb5c29… / b1d7ada3…) dont les étiquettes T9 de mauvaise langue reprennent l'étiquette
# X4-L5 (final-x4-l5, celle d'a-sft), corrections T9 sous prompt EN x3 (g5e_mix.py). Contamination par ligne (leak_check
# drop) du mélange entier, audit_pii et scan à 0. Sur l'hôte de la 3080 : le corpus n'en sort pas.
set -u
K=/root/steph-ft/g5e; R=$K/repo; F=$R/bench/matrix/finetune; V=$R/bench/matrix/v3; D=/root/steph-ft/data
SRC=$D/mix-g5d; OUT=$D/mix-g5e; X4=$D/final-x4-l5; EXTRA=$D/mix-extra-r1
SHA="18bb5c29905c632d705f4235e1d82648beb5beaac671b58d5c4bb702245a12cc b1d7ada3836ab1db7a464e89188c6b97758f3cec9fbc38d2a6e324db4c8bb7aa"
EXTRA_SHA="5a51360159516467ffb489ab1fe908531e7ab2b07f0d6a42baf37740cac5dd1a cb39f6886f9b3db5f91e76f167247874ddb3818a65cf4500b4df8cc0c74e15ce"
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
# liste de noms d'audit_pii copiée chmod 600 par l'appelant, effacée à la fin
trap 'shred -u $HOME/.config/steph/pii_names.tsv 2>/dev/null' EXIT
mkdir -p $K/logs $K/raw; cd $K
[ -f $OUT/train.jsonl ] && exit 0
[ -f $HOME/.config/steph/pii_names.tsv ] || { note "ARRÊT : liste de noms absente"; exit 1; }
[ "$(sha256sum $SRC/train.jsonl $SRC/val.jsonl | cut -d' ' -f1 | paste -sd' ')" = "$SHA" ] || { note "ARRÊT : mix-g5d différent"; exit 1; }
[ "$(sha256sum $EXTRA/train.jsonl $EXTRA/val.jsonl | cut -d' ' -f1 | paste -sd' ')" = "$EXTRA_SHA" ] || { note "ARRÊT : mix-extra-r1 différent"; exit 1; }
(cd $X4 && sha256sum --quiet -c SHA256SUMS) || { note "ARRÊT : final-x4-l5 différent de ses SHA256SUMS"; exit 1; }
PYTHONPATH=$R/bench/matrix/results/finetune/loop/round-3/r3t2p3 python3 $F/g5e/g5e_mix.py $SRC $X4 $EXTRA $K/raw > $K/logs/relabel.json \
  || { note "ARRÊT : g5e_mix.py"; exit 1; }
note "RÉÉTIQUETAGE $(cat $K/logs/relabel.json)"
python3 $V/tools/leak_check.py prints $K/v3prints-head.json $V/cases/*.jsonl $V/cases/dev/*.jsonl $V/cases/test/*.jsonl > /dev/null
mkdir -p $OUT
for f in train val; do
  python3 $V/tools/leak_check.py drop $K/v3prints-head.json $K/raw/$f.jsonl $OUT/$f.jsonl > $K/logs/drop-$f.log
  note "SANS FUITE $f $(cut -c1-160 $K/logs/drop-$f.log)"
done
python3 $F/audit_pii.py $OUT/train.jsonl $OUT/val.jsonl > $K/logs/pii-mix.log 2>&1 || { note "ARRÊT : audit_pii $(tail -1 $K/logs/pii-mix.log)"; rm -rf $OUT; exit 1; }
python3 $V/tools/leak_check.py scan $K/v3prints-head.json $K/logs/leak-mix.json $OUT/train.jsonl $OUT/val.jsonl > $K/logs/leak-mix.log 2>&1
grep -q '"rejected": \[\]' $K/logs/leak-mix.log || { note "ARRÊT : cas du banc dans le mix $(tail -1 $K/logs/leak-mix.log | cut -c1-120)"; rm -rf $OUT; exit 1; }
sha256sum $OUT/*.jsonl $K/raw/*.jsonl > $K/logs/mix-sha.txt
rm -rf $K/raw
note "MIX $(wc -l < $OUT/train.jsonl) / $(wc -l < $OUT/val.jsonl) ; audit_pii $(tail -1 $K/logs/pii-mix.log | cut -c1-60) ; fuite $(tail -1 $K/logs/leak-mix.log | cut -c1-80)"
