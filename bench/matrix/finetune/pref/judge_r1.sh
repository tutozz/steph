#!/bin/bash
# judge_r1.sh <étiquettes...> : juge A7 d'origine revalidé, score v2, inventions sans/avec ancrage, Steph Speak Bench dev, bonne langue.
set -u
R=/root/steph-ft/r1; F=$R/repo/bench/matrix/finetune; E=$R/eval; B=/root/steph-ft/llama.cpp/build/bin
note() { echo "$(date +%H:%M) $*" >> $R/run.done; }
nice -n 10 $B/llama-server -m /root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf --host 127.0.0.1 --port 8931 -ngl 99 -c 16384 \
  --parallel 4 --no-webui --jinja --reasoning-budget 0 > $R/logs/qwen-eval.log 2>&1 < /dev/null &
QP=$!
for i in $(seq 120); do curl -sf http://127.0.0.1:8931/health >/dev/null && break; sleep 2; done
cd /root/steph-ft/judge
python3 validate.py A > $E/validate-A-$(date +%H%M).txt 2>&1; python3 validate.py B > $E/validate-B-$(date +%H%M).txt 2>&1
IDS=build-cmake-missing-package,runtime-command-not-found,runtime-oom-killed,tests-mocha-vitest,disk-smartctl-health,mem-vmstat,hw-lscpu,hw-lsusb,hw-nvidia-smi,hw-system-profiler-macos,ctr-podman-ps-exited,list-grep-functions,long-find-permission-denied,long-rsync-transfer
export PYTHONPATH=/root/steph-ft/judge:$R/repo/src
C=$R/repo/bench/matrix/cases_compact_granite200_train.json
for L in "$@"; do
  ls $E/bench/$L-b7.json >/dev/null 2>&1 || continue
  python3 $F/pref/score_compact.py $C $E/bench/$L-b7.json $E/bench/$L-b42.json $E/bench/$L-b123.json > $E/score-$L.json 2>> $R/logs/eval-judge.log
  [ -f $E/judge-$L.txt ] || python3 $F/pref/judge_bench.py $C $E/judge-$L.json $E/bench/$L-b7.json $E/bench/$L-b42.json $E/bench/$L-b123.json > $E/judge-$L.txt 2>> $R/logs/eval-judge.log
  [ -f $E/judge-$L-ground.txt ] || python3 $F/pref/judge_bench.py $C $E/judge-$L-ground.json $E/bench/$L-b7.json $E/bench/$L-b42.json $E/bench/$L-b123.json --ground > $E/judge-$L-ground.txt 2>> $R/logs/eval-judge.log
  [ -f $E/speak-$L.txt ] || python3 $F/pref/speak_unresolved.py $E/speak/$L/*_$L-steph_fr_dev.json $E/speak/$L/*_$L-steph_en_dev.json --judge --ids $IDS > $E/speak-$L.txt 2>> $R/logs/eval-judge.log
  python3 $F/pref/lang_rate.py $E/speak/$L/*_test.json > $E/lang-$L.txt 2>> $R/logs/eval-judge.log
  note "JUGE $L"
done
kill $QP
