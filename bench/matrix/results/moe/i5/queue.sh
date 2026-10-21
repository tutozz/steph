#!/bin/bash
# G6 : file i5, un modèle après l'autre (g6_i5.sh), reprenable.
cd /root/g6
while read lab repo file sha kind; do
  [ -z "$lab" ] && continue
  grep -q "DONE $lab\$" run.log 2>/dev/null && continue
  bash /root/g6/g6_i5.sh $lab $repo $file $sha $kind
done < "$1"
echo "QUEUEDONE $1" >> run.log
