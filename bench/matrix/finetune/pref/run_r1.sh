#!/bin/bash
# R1 : chain_r1.sh <variante> ; env SFT_LR, MIXARGS (options de compose_r1), EXTRA_PAIRS, REFS=1 pour rebanquer P17 et K3-a.
# mix -> SFT 4 graines (départ P17) -> soupe -> paires DPO (juge A7) -> DPO 60 pas -> GGUF -> bancs -> juges.
set -u
V=$1
R=/root/steph-ft/r1; F=$R/repo/bench/matrix/finetune; E=$R/eval; B=/root/steph-ft/llama.cpp/build/bin
export K3=$R TAG=r1 MIX=$R/mix-$V F16_DIR=/tmp SFT_LR=${SFT_LR:-2e-4}
S=$F/pref/run_k3.sh
note() { echo "$(date +%H:%M) $*" >> $R/run.done; }
cd $R
if [ ! -f mix-extra/train.jsonl ]; then
  for L in fr en; do
    PYTHONPATH=$R/repo/src python3 -c "
import json, sys
sys.path.insert(0, '$F')
from qa_corpus import decide_label
rows = [json.loads(l) for l in open('qa/qa-$L.jsonl')]
keep = [r for r in rows if decide_label(r['_category'], r['messages'][-1]['content'], 'ok', '$L') is not None]
open('qa/qa-$L.filtered.jsonl', 'w').writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in keep)
print('$L', len(rows), len(keep))" >> logs/qa-refilter.txt
  done
  J=feat-en/jd
  PYTHONPATH=$R/repo/src python3 $F/compose_k3.py --qa qa/qa-fr.filtered.jsonl qa/qa-en.filtered.jsonl \
    --feature detail_en=feat-en/detail.en.jsonl --feature start_en=feat-en/start.en.jsonl --feature progress_en=feat-en/progress.en.jsonl \
    --feature-exclude detail_en=$J/rejects-detail-en.txt --feature-exclude start_en=$J/rejects-start-en.txt \
    --feature-exclude progress_en=$J/rejects-progress-en.txt \
    --bench $R/repo/bench/matrix/cases.json --speak-bench $R/repo/benchmark/data/v1 --max-chars 587 --out mix-extra \
    > logs/mix-extra.json 2>&1 || { note "MIX QA KO"; exit 1; }
fi
[ -f mix-$V/train.jsonl ] || python3 $F/compose_r1.py --base /root/steph-ft/k3/mix --extra mix-extra ${MIXARGS:-} --out mix-$V \
  > logs/mix-$V.json 2>&1 || { note "MIX KO $V"; exit 1; }
note "MIX $V $(tail -1 logs/mix-$V.json)"
bash $S sft $V $R/base-p17 && bash $S soup $V $R/base-p17 && bash $S pairs $V $R/base-p17 && bash $S dpo $V $R/base-p17 \
  || { note "CHAÎNE KO $V"; exit 1; }
for T in sft dpo; do bash $F/pref/run_eval_k3.sh $R/gguf/r1-$V-$T-Q4_K_M.gguf r1-$V-$T; done
LABELS="r1-$V-dpo r1-$V-sft"
if [ "${REFS:-0}" = 1 ]; then
  bash $F/pref/run_eval_k3.sh /root/steph-ft/p17/gguf/p17-dpo-lr2e5-ep12-uniform-Q4_K_M.gguf p17
  bash $F/pref/run_eval_k3.sh /root/steph-ft/k3/gguf/k3-a-dpo-Q4_K_M.gguf k3-a-dpo
  LABELS="$LABELS p17 k3-a-dpo"
fi
bash $F/pref/judge_r1.sh $LABELS
note "CHAIN $V"
