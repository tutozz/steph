#!/bin/bash
# G5c : juge fort « juste et utile » (judge_useful_v3.py, google/gemma-4-31b-it de T9, sans raisonnement) sur le TEST de
# décision, graine 7, G5c, a-sft et v1.0 (décision utilisateur du 2026-10-01 : TEST permis pour juger les candidats d'une
# décision, jamais pour étiqueter ; --decision-test laisse une trace au journal de dépense). Contrôles plantés d'abord.
# Poste plafonné par le journal du client ; clé copiée en chmod 600 par l'appelant, effacée à la fin.
#   useful.sh <plafond $>   (sur l'hôte de la 3080, après les runs TEST de eval_3080.sh)
set -u
CAP=$1
K=/root/steph-ft/g5c; T=$K/repo/bench/matrix/v3/tools; U=$K/useful; M=google/gemma-4-31b-it
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
mkdir -p $U; cd $U
trap 'shred -u $HOME/.config/steph/openrouter.key 2>/dev/null' EXIT
[ -f models.json ] || curl -sf https://openrouter.ai/api/v1/models -o models.json || { note "UTILE : liste des modèles KO"; exit 1; }
A="--model $M --models-json models.json --ledger spend.jsonl --cap $CAP"
[ -f controls.json ] || python3 $T/judge_useful_v3.py controls $A --out controls.json > controls.log 2>&1
note "UTILE contrôles rc=$? $(tail -1 controls.log | cut -c1-200)"
R="$K/runs/g5c-test-b7.json $K/runs/a-sft-test-b7.json $K/runs/v10-test-b7.json"
python3 $T/judge_useful_v3.py run $A --split test --decision-test --out verdicts-test.json $R > run-test.log 2>&1
note "UTILE TEST rc=$? $(tail -1 run-test.log | cut -c1-200)"
python3 $T/judge_useful_v3.py report --split test --decision-test --verdicts verdicts-test.json $R > report-test.jsonl 2>&1
python3 $K/repo/bench/matrix/results/g5c/useful_pair.py verdicts-test.json $K/runs test > pair-test.json 2>&1
note "UTILE rapport $(wc -l < report-test.jsonl) lignes, paires $(head -c 120 pair-test.json | tr -d '\n')"
