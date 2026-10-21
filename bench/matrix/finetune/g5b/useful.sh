#!/bin/bash
# G5b : juge fort « juste et utile » (judge_useful_v3.py, google/gemma-4-31b-it de T9, sans raisonnement) sur le DEV,
# graine 7, v1.0, a-sft et G5b ; le TEST est refusé par l'outil (invariant T9 : le split TEST ne part jamais chez un
# fournisseur). Poste plafonné par le journal du client ; clé copiée en chmod 600 par l'appelant, effacée à la fin.
#   useful.sh <plafond $>   (sur l'hôte de la 3080, après eval_3080.sh dev)
set -u
CAP=$1
K=/root/steph-ft/g5b; T=$K/repo/bench/matrix/v3/tools; U=$K/useful; M=google/gemma-4-31b-it
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
mkdir -p $U; cd $U
trap 'shred -u $HOME/.config/steph/openrouter.key 2>/dev/null' EXIT
[ -f models.json ] || curl -sf https://openrouter.ai/api/v1/models -o models.json || { note "UTILE : liste des modèles KO"; exit 1; }
A="--model $M --models-json models.json --ledger spend.jsonl --cap $CAP"
[ -f controls.json ] || python3 $T/judge_useful_v3.py controls $A --out controls.json > controls.log 2>&1
note "UTILE contrôles rc=$? $(tail -1 controls.log | cut -c1-200)"
S=$K/repo/bench/matrix/results/t9/dev-sub.ids
R="$K/runs/g5b-dev-b7.json $K/runs/a-sft-dev-b7.json $K/runs/v10-dev-b7.json"
# 1) sous-échantillon DEV stratifié de T9 (152 évaluations) ; 2) reste du DEV tant que le plafond le permet, G5b d'abord
python3 $T/judge_useful_v3.py run $A --ids $S --out verdicts.json $R > run-sub.log 2>&1
note "UTILE sous-échantillon rc=$? $(tail -1 run-sub.log | cut -c1-200)"
python3 $T/judge_useful_v3.py run $A --out verdicts.json $R > run-all.log 2>&1
note "UTILE DEV rc=$? $(tail -1 run-all.log | cut -c1-200)"
python3 $T/judge_useful_v3.py report --verdicts verdicts.json --ids $S $R > report-sub.jsonl 2>&1
note "UTILE rapport $(wc -l < report-sub.jsonl) lignes"
