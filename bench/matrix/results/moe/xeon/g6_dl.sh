#!/bin/bash
# G6 : téléchargement des GGUF officiels (sha256 vérifié contre Hugging Face) et des poids à convertir.
set -u
D=/root/steph-ft/g6; mkdir -p $D/models $D/hf $D/logs; cd $D
while read repo file size sha; do
  out=models/$file
  if [ ! -f $out ] || [ "$(stat -c %s $out)" != "$size" ]; then
    curl -sL --retry 5 -C - -o $out "https://huggingface.co/$repo/resolve/main/$file"
  fi
  got=$(sha256sum $out | cut -d' ' -f1)
  [ "$got" = "$sha" ] && echo "OK $file $size $sha" || echo "SHA KO $file $got"
done < ggufs.txt
for repo in utter-project/EuroMoE-2.6B-A0.6B-Instruct-2512 ATH-MaaS/Marco-Nano-Instruct; do
  n=${repo#*/}; mkdir -p hf/$n
  for f in $(curl -s "https://huggingface.co/api/models/$repo" | python3 -c "import json,sys;[print(s['rfilename']) for s in json.load(sys.stdin)['siblings'] if not s['rfilename'].endswith(('.md','.png','.jpg','.gitattributes'))]"); do
    mkdir -p hf/$n/$(dirname $f); curl -sL --retry 5 -C - -o hf/$n/$f "https://huggingface.co/$repo/resolve/main/$f"
  done
  echo "HF $n $(du -sh hf/$n | cut -f1)"
done
[ -d llama.cpp ] || git clone -q --depth 1 --branch b11205 https://github.com/ggml-org/llama.cpp.git llama.cpp
echo "SRC $(cd llama.cpp && git log -1 --format=%h)"
echo DLDONE
