#!/usr/bin/env bash
# Banc TTS par niveau, dans des scopes cgroup temporaires, priorité basse.
set -uo pipefail
ROOT=/root/stephbench
PY=$ROOT/venv/bin/python
UV=$ROOT/bin/uv-x86_64-unknown-linux-gnu/uv
M=/mnt/backup-hdd/stephbench-tmp/tts
OUT=$ROOT/results/tts
SAMPLES=$ROOT/results/tts-samples
LOG=$ROOT/logs/tts.log
mkdir -p "$M" "$OUT" "$SAMPLES"
exec >>"$LOG" 2>&1

echo "DEBUT $(date) charge $(cut -d' ' -f1-3 /proc/loadavg)"
VIRTUAL_ENV=$ROOT/venv "$UV" pip install -q piper-tts kokoro-onnx || echo "ECHEC install"

HF=https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR
VOICES="gilles/low mls/medium mls_1840/low siwis/low siwis/medium tom/medium upmc/medium"
for v in $VOICES; do
  name=${v%/*}; q=${v#*/}; f=fr_FR-$name-$q
  [ -f "$M/$f.onnx" ] || { curl -fsSL -o "$M/$f.onnx" "$HF/$name/$q/$f.onnx" && curl -fsSL -o "$M/$f.onnx.json" "$HF/$name/$q/$f.onnx.json"; } || echo "ECHEC voix $f"
done
KR=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
for f in kokoro-v1.0.onnx kokoro-v1.0.int8.onnx voices-v1.0.bin; do
  [ -f "$M/$f" ] || curl -fsSL -o "$M/$f" "$KR/$f" || echo "ECHEC kokoro $f"
done
ls -la "$M"

declare -A CPUS=( [N1]="0,6" [N2]="0,1,6,7" [N3]="0,1,2,3,6,7,8,9" [N4]="0,1,2,3,4,5,6,7,8,9,10,11" )
declare -A THREADS=( [N1]=2 [N2]=2 [N3]=4 [N4]=6 )
declare -A MEM=( [N1]=4G [N2]=4G [N3]=8G [N4]=7G )
declare -A QUOTA=( [N1]="-p CPUQuota=100%" [N2]="" [N3]="" [N4]="" )

run() {  # niveau moteur modèle nom
  local lv=$1 eng=$2 model=$3 name=$4 smp=""
  [ -f "$model" ] || { echo "ABSENT $model"; return; }
  [ "$lv" = N4 ] && smp="$SAMPLES/${eng}_${name}.wav"
  while awk -v l="$(cut -d' ' -f1 /proc/loadavg)" 'BEGIN{exit !(l>4)}'; do echo "charge haute, attente"; sleep 30; done
  timeout 600 systemd-run --scope --quiet -p AllowedCPUs="${CPUS[$lv]}" ${QUOTA[$lv]} -p MemoryMax="${MEM[$lv]}" \
    nice -n 19 "$PY" "$ROOT/scripts/tts_bench.py" "$eng" "$model" "${THREADS[$lv]}" "${lv}_${eng}_${name}" \
    "$OUT/${lv}_${eng}_${name}.json" $smp || echo "ECHEC ${lv}_${eng}_${name}"
}

for lv in N1 N2 N3 N4; do
  for v in $VOICES; do name=${v%/*}-${v#*/}; run "$lv" piper "$M/fr_FR-$name.onnx" "$name"; done
  run "$lv" kokoro "$M/kokoro-v1.0.int8.onnx" int8
  run "$lv" kokoro "$M/kokoro-v1.0.onnx" fp32
done

for w in "$SAMPLES"/*.wav; do ffmpeg -loglevel error -y -i "$w" -ac 1 -b:a 64k "${w%.wav}.mp3" && rm "$w"; done
echo "FIN $(date) charge $(cut -d' ' -f1-3 /proc/loadavg)"
