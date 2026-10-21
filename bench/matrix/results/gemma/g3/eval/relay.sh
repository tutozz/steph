#!/bin/bash
# Relaie les runs finis de la 3080 vers le juge de la 3060 (petits JSON, aucun calcul local).
L=${RELAY_DIR:-$(dirname "$0")/relay}
mkdir -p $L
: "${GEN:?hôte de la 3080}" "${JUDGE:?hôte de la 3060}"
while :; do
  for f in $(ssh $GEN 'cd /root/steph-ft/g3/eval/runs && ls *-test-b*.json 2>/dev/null | grep -v progress'); do
    [ -f $L/$f.done ] && continue
    scp -3 -q $GEN:/root/steph-ft/g3/eval/runs/$f $JUDGE:/mnt/backup-hdd/stephbench-tmp/gemma/g3/judge-test/runs/$f.tmp && \
      ssh $JUDGE "mv /mnt/backup-hdd/stephbench-tmp/gemma/g3/judge-test/runs/$f.tmp /mnt/backup-hdd/stephbench-tmp/gemma/g3/judge-test/runs/$f" && touch $L/$f.done && echo "$(date +%T) $f"
  done
  [ $(ls $L/*.done 2>/dev/null | wc -l) -ge 15 ] && break
  sleep 120
done
