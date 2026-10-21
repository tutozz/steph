#!/bin/bash
# G5e : juge fort « juste et utile » (judge_useful_v3.py, google/gemma-4-31b-it, sans raisonnement) sur le TEST de
# décision, graine 7 (décision utilisateur du 2026-10-01 : TEST permis pour juger les candidats d'une décision, jamais
# pour étiqueter). Les verdicts de G5c servent de départ : seules les réponses de G5e absentes du fichier sont jugées
# (a-sft regénéré à l'identique, G5c repris). Contrôles plantés d'abord. Journal de dépense propre à G5e, plafonné ; clé
# copiée en chmod 600 par l'appelant, effacée à la fin.
#   useful.sh <plafond $>   (sur l'hôte de la 3080, après eval_3080.sh test)
set -u
CAP=$1
K=/root/steph-ft/g5e; T=$K/repo/bench/matrix/v3/tools; U=$K/useful; M=google/gemma-4-31b-it; C=/root/steph-ft/g5c/useful
note() { echo "$(date '+%d %H:%M') $*" >> $K/run.done; }
mkdir -p $U; cd $U
trap 'shred -u $HOME/.config/steph/openrouter.key 2>/dev/null' EXIT
[ -f models.json ] || curl -sf https://openrouter.ai/api/v1/models -o models.json || { note "UTILE : liste des modèles KO"; exit 1; }
[ -f verdicts-test.json ] || cp $C/verdicts-test.json verdicts-test.json
A="--model $M --models-json models.json --ledger spend.jsonl --cap $CAP"
[ -f controls.json ] || python3 $T/judge_useful_v3.py controls $A --out controls.json > controls.log 2>&1
note "UTILE contrôles rc=$? $(tail -1 controls.log | cut -c1-200)"
R="$K/runs/g5e-test-b7.json $K/runs/a-sft-test-b7.json $K/runs/g5c-test-b7.json"
python3 $T/judge_useful_v3.py run $A --split test --decision-test --out verdicts-test.json $R > run-test.log 2>&1
note "UTILE TEST rc=$? $(tail -1 run-test.log | cut -c1-200)"
python3 $T/judge_useful_v3.py report --split test --decision-test --verdicts verdicts-test.json $R > report-test.jsonl 2>&1
python3 $K/repo/bench/matrix/results/g5e/useful_pair.py verdicts-test.json $K/runs test > pair-test.json 2>&1
note "UTILE rapport $(wc -l < report-test.jsonl) lignes, paires $(head -c 120 pair-test.json | tr -d '\n')"
