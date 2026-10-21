#!/bin/bash
# X3 : Qwen3.5 9B brut, seul sur l'A1000 après les autres couloirs ; tout sur la carte si ça tient, sinon 24 couches.
D=/root/steph-ft/loop/x3
until [ $(grep -h LANEDONE $D/logs/lane-896[123].log | wc -l) = 3 ]; do sleep 60; done
echo "qwen3.5-9b $D/raw/Qwen3.5-9B-Q4_K_M.gguf gen 99" > $D/models-9b.txt
bash $D/lane.sh $D/models-9b.txt 8965 7
if [ ! -f $D/runs/qwen3.5-9b-test-b7.json ]; then
  echo "qwen3.5-9b $D/raw/Qwen3.5-9B-Q4_K_M.gguf gen 24" > $D/models-9b.txt
fi
bash $D/lane.sh $D/models-9b.txt 8965 7 42 123
