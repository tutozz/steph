#!/bin/bash
# R1 : questions FR supplémentaires et questions EN, enseignant et juge A7 d'origine (Qwen3.5-9B) sur la 3080.
set -u
R=/root/steph-ft/r1; F=$R/repo/bench/matrix/finetune; C=/root/steph-ft/data/corpus; S=/root/steph-ft/data/snapshot-1/clean
B=/root/steph-ft/llama.cpp/build/bin
mkdir -p $R/qa $R/logs
note() { echo "$(date +%H:%M) $*" >> $R/run.done; }
$B/llama-server -m /root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf --host 127.0.0.1 --port 8931 -ngl 99 -c 32768 \
  --parallel 4 --no-webui --jinja --reasoning-budget 0 > $R/logs/qwen-qa.log 2>&1 < /dev/null &
echo $! > $R/qwen.pid
for i in $(seq 120); do curl -sf http://127.0.0.1:8931/health >/dev/null && break; sleep 2; done
cd /root/steph-ft/judge
python3 validate.py A > $R/qa/validate-A.txt 2>&1; python3 validate.py B > $R/qa/validate-B.txt 2>&1
note "JUGE VALIDE $(grep -c . $R/qa/validate-A.txt)"
gen() {  # langue graine n corpus...
  local L=$1 SD=$2 N=$3; shift 3
  python3 -c "import runpy, sys; sys.path.insert(0, '/root/steph-ft/judge'); sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')" \
    $F/qa_corpus.py --corpus "$@" --bench $R/repo/bench/matrix/cases.json --out $R/qa/qa-$L.jsonl --n $N --seed $SD \
    --lang $L --error-weight 3 --teacher-port 8931 > $R/logs/qa-$L.log 2>&1 || note "QA KO $L"
  note "QA $L $(tail -1 $R/logs/qa-$L.log)"
}
gen fr 7 240 $C/linux-dev.jsonl $C/linux-low.jsonl $C/macos.jsonl $S/*.jsonl &
G1=$!
gen en 42 330 $C/linux-dev.jsonl $C/linux-low.jsonl $C/macos.jsonl $C/linux-low.en.jsonl $C/macos.en.jsonl $S/*.jsonl &
wait $G1 $!
kill $(cat $R/qwen.pid)
note QA-DONE
