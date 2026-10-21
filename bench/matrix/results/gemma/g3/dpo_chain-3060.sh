#!/bin/bash
W=/mnt/backup-hdd/stephbench-tmp/gemma/g3
until [ -f $W/sft-s42-Q4_0.gguf ]; do sleep 30; done
$W/dpo.sh sample $W/sft-s42-Q4_0.gguf && $W/dpo.sh judge && $W/dpo.sh build && $W/dpo.sh train 42 $W/sft-s42/adapter
