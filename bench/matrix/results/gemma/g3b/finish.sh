#!/bin/bash
# G3b : après le SFT de la 3060, adaptateur -> xeon (fusion, GGUF f16, Q4_0 sans imatrix) -> 3080 (runs G3b) ; les
# machines ne se voient pas : flux ssh à travers la machine qui lance ce script, rien d'écrit sur son disque.
#   GPU3060=... CPU=... GEN=... finish.sh
set -u
: "${GPU3060:?}" "${CPU:?}" "${GEN:?}"
G=/mnt/backup-hdd/stephbench-tmp/gemma/g3b; H=/root/steph-ft/g3b
until ssh $GPU3060 "grep -q 'SFT rc=0' $G/run.done"; do sleep 60; done
ssh $GPU3060 "cd $G/sft-s42 && tar -c adapter" | ssh $CPU "mkdir -p $H/adapters/g3b-s42 && tar -x -C $H/adapters/g3b-s42 --strip-components=1"
echo "$(date +%T) adaptateur $(ssh $CPU "sha256sum $H/adapters/g3b-s42/adapter_model.safetensors | cut -c1-16") ; 3060 $(ssh $GPU3060 "sha256sum $G/sft-s42/adapter/adapter_model.safetensors | cut -c1-16")"
ssh $CPU "cd $H && ./chain.sh g3b adapters/g3b-s42"
ssh $CPU "cat $H/gguf/g3b-Q4_0.gguf" | ssh $GEN "cat > /dev/shm/g3b-Q4_0.gguf.tmp && mv /dev/shm/g3b-Q4_0.gguf.tmp /dev/shm/g3b-Q4_0.gguf"
a=$(ssh $CPU "sha256sum $H/gguf/g3b-Q4_0.gguf | cut -d' ' -f1"); b=$(ssh $GEN "sha256sum /dev/shm/g3b-Q4_0.gguf | cut -d' ' -f1")
echo "$(date +%T) Q4_0 xeon $a 3080 $b"
[ "$a" = "$b" ] || { echo "ARRÊT : copie différente"; exit 1; }
ssh $GEN "systemctl is-active -q ollama && { systemctl stop ollama; echo \"\$(date +%T) ollama arrêté par G3b\" >> $H/logs/done.log; }; ln -sf /dev/shm/g3b-Q4_0.gguf $H/gguf/g3b.gguf && touch $H/gguf/g3b.ok"
echo "$(date +%T) G3b visible par les couloirs de la 3080"
