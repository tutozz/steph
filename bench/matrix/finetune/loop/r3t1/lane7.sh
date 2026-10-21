#!/bin/bash
# R3-T1 : dense replié, split test v3 0db04fa, graine 7, A1000 Vulkan b11205 ; une seule file (machine partagée avec X3).
D=/root/steph-ft/loop/r3t1
python3 $D/bench_run.py --server /root/steph-ft/llama/vulkan/llama-server --model $D/gguf/dense-fold-up2-Q4_K_M.gguf \
  --label dense-fold2-v3test-b7 --cases $D/test/test.json --maxc 0 --port 8981 --ngl 99 --device Vulkan1 \
  --payload "{\"seed\": 7}" --out $D/test/runs/dense-fold2-test-b7.json >> $D/test/lane-7.log 2>&1
echo DONE >> $D/test/lane-7.log
