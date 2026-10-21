#!/bin/bash
# Pilote un entraînement LoRA à distance : écrit control.json ou lit status.json par ssh.
#   bench/matrix/finetune/train_control.sh <hôte> <dossier> stop|slower|eval|status
set -euo pipefail

usage() { echo "usage : $0 <hôte> <dossier> stop|slower|eval|status" >&2; exit 2; }
[ $# -eq 3 ] || usage
HOST=$1 DIR=$2 ACTION=$3

# Mêmes hôtes à mot de passe que sync.sh, pour sshpass sur les machines sans clé.
HOSTS_FILE=${STEPH_LAB_HOSTS:-$HOME/.config/steph/lab_hosts.sh}
[ -f "$HOSTS_FILE" ] || { echo "Fichier d'hôtes introuvable : $HOSTS_FILE" >&2; exit 2; }
# shellcheck source=/dev/null
. "$HOSTS_FILE"

ssh_cmd=(ssh -o ConnectTimeout=10)
[[ " ${PASSWORD_HOSTS[*]:-} " == *" $HOST "* ]] && ssh_cmd=(sshpass -e ssh -o ConnectTimeout=10 -o PubkeyAuthentication=no)

write_control() {  # payload JSON
  "${ssh_cmd[@]}" "$HOST" "mkdir -p '$DIR' && cat > '$DIR/control.json'" <<< "$1"
}

case "$ACTION" in
  stop)   write_control '{"action": "stop"}'
          echo "arrêt demandé sur $HOST:$DIR" ;;
  slower) write_control '{"lr_scale": 0.5}'
          echo "taux d'apprentissage divisé par 2 sur $HOST:$DIR" ;;
  eval)   write_control '{"eval_now": true}'
          echo "évaluation forcée sur $HOST:$DIR" ;;
  status) "${ssh_cmd[@]}" "$HOST" "cat '$DIR/status.json'" 2>/dev/null \
            || echo "aucun statut : entraînement pas encore démarré ou dossier introuvable ($HOST:$DIR)" ;;
  *) usage ;;
esac
