#!/bin/sh
# Steph Speak Bench, protocole steph, split test, FR puis EN, comme bench/matrix/finetune/g5/speak.sh
export HOME=/root/steph-z9/home CUDA_DEVICE_ORDER=PCI_BUS_ID
S=$HOME/.local/share/steph/src
M=$HOME/.local/share/steph/models
F=$S/bench/matrix/finetune
O=/root/steph-z9/out/speak
mkdir -p $O
one() { # label gguf ngl visible hardware
  CUDA_VISIBLE_DEVICES=$4 nice -n 10 /root/steph-z9/bin/llama-server -m $2 --host 127.0.0.1 --port 8894 -c 4096 -ngl $3 --no-webui --jinja --parallel 1 --cache-ram 0 -t 6 > $O/$1.server.log 2>&1 < /dev/null &
  SP=$!
  for i in $(seq 120); do curl -sf http://127.0.0.1:8894/health >/dev/null && break; sleep 1; done
  nvidia-smi --query-gpu=index,memory.used --format=csv,noheader > $O/$1.vram-during.txt
  for spec in fr:train_system_prompt.txt en:train_system_prompt.en.txt; do
    python3 $S/benchmark/run.py --base-url http://127.0.0.1:8894/v1 --model steph --label $1 --out $O --quiet --hardware "$5" --notes "Z9, steph protocol, llama.cpp b11796" --lang ${spec%%:*} --split test --system-prompt-file $F/${spec#*:} >> $O/$1.log 2>&1
  done
  kill $SP; wait $SP 2>/dev/null
}
one small-gpu $M/steph-speak-granite-4.0-h-350M-sft-v2.0-Q4_K_M.gguf 99 1 "RTX 3080 CUDA (partagee avec la passerelle de prod), Ryzen 5 5600"
one small-cpu $M/steph-speak-granite-4.0-h-350M-sft-v2.0-Q4_K_M.gguf 0 -1 "Ryzen 5 5600, 6 threads, CPU seul"
one base-cpu $M/steph-speak-gemma-4-E2B-sft-v2.0-off-ple3.gguf 0 -1 "Ryzen 5 5600, 6 threads, CPU seul"
echo done > $O/speak.done
