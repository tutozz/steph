#!/bin/bash
# R3-T1 : après lane7.sh, même couloir : dense d'origine sans coopmat (GGML_VK_DISABLE_COOPMAT=1), puis dense replié graines 42 et 123.
D=/root/steph-ft/loop/r3t1; L=$D/test/lane-7.log
while ! grep -q DONE $L 2>/dev/null; do sleep 20; done
run() { local lab=$1 m=$2 sd=$3; shift 3
  OUT=$D/test/runs/$lab-test-b$sd.json; [ -f $OUT ] && return
  env "$@" python3 $D/bench_run.py --server /root/steph-ft/llama/vulkan/llama-server --model $m \
    --label $lab-v3test-b$sd --cases $D/test/test.json --maxc 0 --port 8981 --ngl 99 --device Vulkan1 \
    --payload "{\"seed\": $sd}" --out $OUT >> $D/test/lane-7b.log 2>&1
}
run dense-nocm $D/dense.gguf 7 GGML_VK_DISABLE_COOPMAT=1
run dense-fold2 $D/gguf/dense-fold-up2-Q4_K_M.gguf 42 X=1
run dense-fold2 $D/gguf/dense-fold-up2-Q4_K_M.gguf 123 X=1
echo DONE >> $D/test/lane-7b.log
