#!/bin/bash
# G3b : relaie les runs finis de la machine du banc (3080, l'A1000 au départ) vers le juge de la 3060 ; elles ne se voient pas, les petits JSON passent
# par la machine qui lance ce script, copie temporaire effacée aussitôt, aucun calcul local.
set -u
L=${RELAY_DIR:?dossier de marqueurs}; mkdir -p $L
: "${GEN:?hôte du banc}" "${JUDGE:?hôte de la 3060}"
A=${SSHPASS:+sshpass -e}; W=/root/steph-ft/g3b; J=/mnt/backup-hdd/stephbench-tmp/gemma/g3b/judge-test/runs
ssh $JUDGE "mkdir -p $J"
while :; do
  for f in $($A ssh $GEN "cd $W/runs && for p in *-test-b*.json; do case \$p in *.progress.json) ;; *) m=\${p%-test-b*}; s=\${p##*-test-b}; grep -q \"\$m b\${s%.json} rc=0\" $W/logs/done.log && echo \$p;; esac; done"); do
    [ -f $L/$f.done ] && continue
    $A scp -q $GEN:$W/runs/$f $L/$f && scp -q $L/$f $JUDGE:$J/$f.tmp && ssh $JUDGE "mv $J/$f.tmp $J/$f" && touch $L/$f.done && echo "$(date +%T) $f"
    rm -f $L/$f
  done
  [ $(ls $L/*.done 2>/dev/null | wc -l) -ge 12 ] && break
  sleep 120
done
