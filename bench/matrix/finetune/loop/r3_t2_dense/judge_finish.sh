#!/bin/bash
# R3-T2 partie 2 : fin du juge sur la 3080 : tout le reste (part 3 de 4), puis les erreurs à 2 fentes, puis R1 rejugé
# dans cette session (cache séparé, contrôle d'accord avec les verdicts de la partie 3).
W=/root/steph-ft/loop/r3t2p2/jdg; J="bash $W/code/judge.sh $W /root/steph-ft/llama.cpp/build/bin/llama-server /root/steph-ft/models/Qwen3.5-9B-Q4_K_M.gguf 8985"
cd $W
$J 0 1 runs/*.json
PARALLEL=2 $J 0 1 runs/*.json
CACHE=judge/cache-r1 $J 0 1 runs/r1s2-dev-b7.json runs/r1s2-dev-b42.json
echo "$(date +%H:%M) FIN JUGE" >> $W/run.done
