#!/bin/bash
# G6 : essai de fumée, 6 cas dev generic par modèle, sorties affichées.
D=/root/steph-ft/g6; cd $D; export LD_LIBRARY_PATH=/root/steph-ft/vendor/lib
python3 -c "
import json,random
r=json.load(open('in/x3/harness/dev.generic.json'))
out=[]
for k in ('summary','qa'):
  for lang in ('fr','en'):
    xs=[x for x in r if x['kind']==k and x['id'].endswith('@'+lang) and x['reaches_model']]
    out+=xs[5:8] if k=='summary' else xs[3:4]
json.dump(out,open('smoke_cases.json','w'),ensure_ascii=False)"
for g in "$@"; do
  n=$(basename $g .gguf)
  systemd-run --scope -q -p AllowedCPUs=0-31 -p MemoryMax=48G nice -n 19 python3 bench_run.py --server /root/steph-ft/llama/llama-b11205/llama-server \
    --model $g --label smoke-$n --cases smoke_cases.json --maxc 0 --port 8990 --ngl 0 --threads 16 --abort-ttft 120 --out smoke/$n.json > smoke/$n.log 2>&1
  python3 -c "
import json;d=json.load(open('smoke/$n.json'))
print('==', '$n', 'load', d.get('load_s'), 'err', d.get('error'), 'ttft', d.get('ttft_median'), 'gen', d.get('gen_tok_s_median'))
for r in d['rows']: print(r['id'], r.get('prompt_n'), '|', (r.get('out') or r.get('error'))[:300].replace(chr(10),' / '))"
done
