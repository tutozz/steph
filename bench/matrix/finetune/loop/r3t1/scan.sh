#!/bin/bash
# Maxima d activations du dense sur CPU, 50 prompts dev réels, couches 0 à 27.
cd /root/steph-ft/loop/r3t1; export LD_LIBRARY_PATH=src/build/bin; mkdir -p scan
for i in $(seq 0 49); do
  nice -n 10 src/build/bin/llama-eval-callback -m ${M:-dense.gguf} -f ec2/prompt$i.txt -n 1 --temp 0 -t 8 --device none -c 4096 2>&1 | awk "/common_debug_cb_eval:/{n=\$2} /maxabs/{print n, \$3}" | grep -E "^(ffn_swiglu|ffn_out|attn_out|kqv_out|l_out|ffn_up|ffn_gate)-" > scan/${TAG:-cpu}-$i.txt
done
echo DONE > scan/${TAG:-cpu}.done
