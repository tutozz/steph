#!/bin/bash
# G4 : relaie les runs finis de la 3080 vers le juge de la 3060 (petits JSON, aucun calcul local). relay.sh <nombre attendu>
L=$(dirname "$0")/relay; mkdir -p $L; : "${G:?hôte de la 3080}" "${J:?hôte de la 3060}"; D=/mnt/backup-hdd/stephbench-tmp/gemma/g3/judge-test/runs
while :; do
  for f in $(ssh $G 'cd /root/steph-ft/g4/runs && ls g4-*-test-b*.json 2>/dev/null | grep -v progress'); do
    [ -f $L/$f.done ] && continue
    ssh $G "grep -q '\"ram_peak_mb\"' /root/steph-ft/g4/runs/$f" || continue
    scp -3 -q $G:/root/steph-ft/g4/runs/$f $J:$D/$f.tmp && ssh $J "mv $D/$f.tmp $D/$f" && touch $L/$f.done && echo "$(date +%T) $f"
  done
  [ $(ls $L/*.done 2>/dev/null | wc -l) -ge $1 ] && break
  sleep 120
done
