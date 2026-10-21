#!/bin/bash
# R1 : détail, début et progression en anglais sur les captures EN de K2 : entrées de production anglaises,
# enseignant Qwen3.5-9B (label_features --lang en), juge A7 d'origine 2 passes.
set -u
R=/root/steph-ft/r1; F=$R/repo/bench/matrix/finetune; B=/root/steph-ft/llama.cpp/build/bin; W=$R/feat-en
mkdir -p $W/jd $R/judge
note() { echo "$(date +%H:%M) $*" >> $R/run.done; }
until grep -q QA-DONE $R/run.done; do sleep 30; done
export PYTHONPATH=$R/repo/src
: > $W/empty-names.tsv
python3 $F/build_feature_corpus.py --lang en --corpus-dir /root/steph-ft/data/corpus --out-dir $W/in \
  --n-detail 320 --n-start 220 --n-progress-sources 80 --names $W/empty-names.tsv > $R/logs/feat-en-build.log 2>&1 || { note "FEAT EN BUILD KO"; exit 1; }
$B/llama-server -m /root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf --host 127.0.0.1 --port 8931 -ngl 99 -c 32768 \
  --parallel 4 --no-webui --jinja --reasoning-budget 0 > $R/logs/qwen-feat.log 2>&1 < /dev/null &
QP=$!
for i in $(seq 120); do curl -sf http://127.0.0.1:8931/health >/dev/null && break; sleep 2; done
cp /root/steph-ft/judge/judge_lib.py $R/repo/bench/matrix/finetune/judge_corpus_2pass.py $R/judge/
for M in detail start progress; do
  python3 $F/label_features.py --in $W/in/$M.en.jsonl --mode $M --lang en --out $W/$M.en.raw.jsonl --port 8931 \
    --parallel 4 --max-tokens 160 > $R/logs/feat-en-$M.log 2>&1 || { note "LABEL EN KO $M"; continue; }
  # sortie de label_features -> {source, messages: train_messages}, la forme que lit judge_corpus_2pass
  python3 -c "import json, sys
with open(sys.argv[2], 'w') as out:
    for l in open(sys.argv[1]):
        r = json.loads(l)
        out.write(json.dumps({'source': r['source'], 'messages': r['train_messages']}, ensure_ascii=False) + '\n')" \
    $W/$M.en.raw.jsonl $W/$M.en.jsonl
  (cd $R/judge && python3 judge_corpus_2pass.py $W/$M.en.jsonl $M-en $W/jd > $R/logs/judge-feat-en-$M.log 2>&1) || note "JUGE EN KO $M"
  note "FEAT EN $M $(tail -1 $R/logs/feat-en-$M.log | tr -d '\n') $(tail -1 $R/logs/judge-feat-en-$M.log | cut -c1-200)"
done
kill $QP
note FEAT-EN-DONE
