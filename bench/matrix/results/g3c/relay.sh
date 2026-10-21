#!/bin/bash
# G3c, relais depuis le Mac (ssh seulement, aucun fichier écrit ici hors ce journal) : pour chaque run, attend la fin du SFT
# sur la 3060, enchaîne finish.sh (adaptateur -> xeon chain.sh -> Q4_0 vers la 3080), puis le contrôle DEV de la 3080
# sur G3b et tous les runs prêts (runs et verdicts déjà faits repris du cache).
#   relay.sh <run>...   (ex. s42 t9s42 t9s7)
set -u
D=$(cd "$(dirname "$0")" && pwd); GEN=user@host; LOG=${RELAY_LOG:-/tmp/g3c-relay.log}
done_models="g3b"
for r in "$@"; do
  echo "$(date '+%d %H:%M') relais $r : attente du SFT" >> $LOG
  bash $D/finish.sh $r >> $LOG 2>&1 || { echo "$(date '+%d %H:%M') ARRÊT relais $r" >> $LOG; exit 1; }
  done_models="$done_models g3c-$r"
  ssh $GEN "bash /root/steph-ft/g3c/ft/dev-3080.sh $done_models" >> $LOG 2>&1
  echo "$(date '+%d %H:%M') DEV fait : $done_models" >> $LOG
done
echo "$(date '+%d %H:%M') relais FIN" >> $LOG
