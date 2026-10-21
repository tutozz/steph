#!/bin/bash
# Copies the anonymized fine-tuning data to the lab machines. Run by the user, never by an agent.
#   bench/matrix/finetune/sync.sh corpus   -> audited corpus to the two labeling GPUs
#   bench/matrix/finetune/sync.sh labels   -> labeled data back to the Mac, finalized and audited, then to every trainer
#   bench/matrix/finetune/sync.sh qa       -> P15a question file back to the Mac, audited with the private name list, then to every trainer
#   bench/matrix/finetune/sync.sh relabel  -> X4 corpus relabeled by the 27B back to the Mac, audited with the private name list, then to every trainer
#   bench/matrix/finetune/sync.sh mixextra -> R1 mix-extra (EN questions and features) from its trainer to the Mac, audited, then to every trainer
#   MIX_SOURCE=host:dir MIX_NAME=name bench/matrix/finetune/sync.sh mix -> a built training mix to the Mac, audited, then to every trainer under <name>
set -euo pipefail
cd "$(dirname "$0")"
HERE=$PWD

# Real host names stay out of the repo: LABELERS, TRAINERS and PASSWORD_HOSTS come from this file.
HOSTS_FILE=${STEPH_LAB_HOSTS:-$HOME/.config/steph/lab_hosts.sh}
[ -f "$HOSTS_FILE" ] || { echo "Fichier d'hôtes introuvable : $HOSTS_FILE" >&2; exit 2; }
# shellcheck source=/dev/null
. "$HOSTS_FILE"

audit() {
  python3 "$HERE/audit_pii.py" "$@" || { echo "Audit d'anonymisation en échec : rien n'est copié." >&2; exit 1; }
}

push() {  # destination, files...
  local host=${1%%:*} dir=${1#*:}; shift
  local ssh_cmd=(ssh)
  [[ " ${PASSWORD_HOSTS[*]:-} " == *" $host "* ]] && ssh_cmd=(sshpass -p root ssh -o PubkeyAuthentication=no)
  # tar over ssh: some lab machines have no rsync
  COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -cf - "$@" | "${ssh_cmd[@]}" "$host" "mkdir -p $dir && tar xf - -C $dir"
  echo "copié vers $host:$dir"
}

case "${1:-}" in
  corpus)
    # corpus/features/*.jsonl (H3a) : entrées détail/début/progression/flux/résidu
    # résumé déjà construites au format exact de steph (build_feature_corpus.py),
    # prêtes pour label_features.py côté labeleur - pas de nouvelle passe d'audit
    # nécessaire côté labeleur, elles sortent déjà de l'audit ci-dessous.
    files=(snapshot-1/clean/*.jsonl corpus/*.jsonl corpus/features/*.jsonl)
    audit "${files[@]}"
    for dest in "${LABELERS[@]}"; do push "$dest" "${files[@]}"; done ;;
  labels)
    mkdir -p labeled/raw
    for dest in "${LABELERS[@]}"; do rsync -a --exclude train.jsonl "${dest%%:*}:${dest#*:}/labeled/" labeled/raw/ || true; done
    rm -f labeled/*.jsonl
    python3 finalize_labels.py labeled/raw labeled
    # finalized files go to <dir>/final/, never back into the labelers' raw labeled/ folder
    cd labeled
    files=(*.jsonl)
    audit "${files[@]}"
    for dest in "${TRAINERS[@]}"; do push "${dest}/final" "${files[@]}"; done ;;
  qa)
    # The question file was generated on the first labeler; its scanner there never saw the private name list.
    qa_source=${QA_SOURCE:-${LABELERS[0]%%:*}:/root/stephbench-matrix/qa-p15a/qa_train.jsonl}
    qa_dir=${STEPH_QA_DIR:-labeled/qa}
    mkdir -p "$qa_dir"
    ssh "${qa_source%%:*}" "cat ${qa_source#*:}" > "$qa_dir/qa_train.jsonl.part"
    mv "$qa_dir/qa_train.jsonl.part" "$qa_dir/qa_train.jsonl"
    cd "$qa_dir"
    [ -s qa_train.jsonl ] || { echo "Fichier de questions vide : rien n'est copié." >&2; exit 1; }
    echo "$(wc -l < qa_train.jsonl | tr -d ' ') exemples rapatriés"
    audit qa_train.jsonl
    for dest in "${TRAINERS[@]}"; do push "${dest}/final" qa_train.jsonl; done ;;
  relabel)
    # X4 relabeled on a CPU host that never saw the private name list; X4_SOURCE (host:dir) comes from the hosts file
    [ -n "${X4_SOURCE:-}" ] || { echo "X4_SOURCE absent du fichier d'hôtes (ex. root@hote:/root/steph-ft/x4/final)." >&2; exit 2; }
    mkdir -p labeled/x4
    rsync -a "${X4_SOURCE%/}/" labeled/x4/
    cd labeled/x4
    shasum -a 256 -c SHA256SUMS
    files=(*.jsonl)
    audit "${files[@]}"
    for dest in "${TRAINERS[@]}"; do push "${dest}/final-x4" "${files[@]}" README.txt SHA256SUMS; done ;;
  mixextra)
    # R1 mix-extra exists on one trainer only; MIXEXTRA_SOURCE (host:dir) comes from the hosts file
    [ -n "${MIXEXTRA_SOURCE:-}" ] || { echo "MIXEXTRA_SOURCE absent du fichier d'hôtes (ex. root@hote:/root/steph-ft/r1/mix-extra)." >&2; exit 2; }
    mkdir -p labeled/mix-extra
    rsync -a "${MIXEXTRA_SOURCE%/}/" labeled/mix-extra/
    cd labeled/mix-extra
    files=(*.jsonl)
    audit "${files[@]}"
    for dest in "${TRAINERS[@]}"; do push "${dest}/mix-extra-r1" "${files[@]}"; done ;;
  mix)
    # a training mix built on one trainer (e.g. G5c on the 3060), needed on another GPU
    [ -n "${MIX_SOURCE:-}" ] && [ -n "${MIX_NAME:-}" ] || { echo "MIX_SOURCE (hôte:dossier) et MIX_NAME requis." >&2; exit 2; }
    mkdir -p "labeled/mix-$MIX_NAME"
    rsync -a "${MIX_SOURCE%/}/" "labeled/mix-$MIX_NAME/"
    cd "labeled/mix-$MIX_NAME"
    files=(*.jsonl)
    audit "${files[@]}"
    for dest in "${TRAINERS[@]}"; do push "${dest}/mix-$MIX_NAME" "${files[@]}" || echo "copie impossible vers $dest, machine suivante" >&2; done ;;
  *) echo "usage : $0 corpus|labels|qa|relabel|mixextra|mix" >&2; exit 2 ;;
esac
