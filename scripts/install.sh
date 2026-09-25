#!/usr/bin/env bash
# Installe tout ce qu'il faut à steph, sans droits root :
#   - llama.cpp (build CUDA si carte NVIDIA, sinon Vulkan, sinon CPU)
#   - le modèle GGUF (Gemma 4 E2B par défaut, STEPH_MODEL=qwen pour Qwen3.5 2B)
#   - la voix Piper française
#   - la commande `steph` dans ~/.local/bin
set -euo pipefail
cd "$(dirname "$0")/.."
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/steph"
mkdir -p "$DATA/models" "$DATA/voices" vendor/llama
CURL=(curl -q -fL --retry 3)   # -q : ignore ~/.curlrc

OS=$(uname -s)

# « releases/latest » peut pointer sur une release sans binaires (v0.5.0) :
# on prend la plus récente qui publie réellement l'archive voulue.
llama_tag() {
  "${CURL[@]}" -s "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=30" | python3 -c '
import json, sys
flavor = sys.argv[1]
for r in json.load(sys.stdin):
    t = r["tag_name"]
    if any(a["name"] == f"llama-{t}-bin-{flavor}.tar.gz" for a in r["assets"]):
        print(t); break
else:
    sys.exit(f"aucune release llama.cpp ne publie le binaire {flavor}")
' "$1"
}

# --- llama.cpp -------------------------------------------------------------
if [ "$OS" = Darwin ] && ! command -v llama-server >/dev/null && ! ls vendor/llama/llama-*/llama-server >/dev/null 2>&1; then
  # macOS : Homebrew si présent (Metal inclus), sinon binaire officiel
  if command -v brew >/dev/null; then
    brew install llama.cpp
  else
    ARCH=$([ "$(uname -m)" = arm64 ] && echo arm64 || echo x64)
    TAG=$(llama_tag "macos-$ARCH")
    "${CURL[@]}" -o /tmp/llama.tgz "https://github.com/ggml-org/llama.cpp/releases/download/$TAG/llama-$TAG-bin-macos-$ARCH.tar.gz"
    tar xzf /tmp/llama.tgz -C vendor/llama && rm /tmp/llama.tgz
    # les bibliothèques peuvent être rangées à part : on les met à côté du binaire
    D=$(dirname "$(ls vendor/llama/*/llama-server vendor/llama/*/*/llama-server 2>/dev/null | head -1)")
    [ "$(basename "$D")" = bin ] && mv "$D"/* "$D/.." 2>/dev/null || true
    xattr -dr com.apple.quarantine vendor/llama 2>/dev/null || true
  fi
  command -v sox >/dev/null || echo "Conseil : brew install sox (voix plus réactive qu'avec afplay)"
elif [ "$OS" != Darwin ] && ! ls vendor/llama/llama-*/llama-server >/dev/null 2>&1; then
  if command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then
    FLAVOR=ubuntu-cuda-12.8-x64; EXTRA=1
  elif [ -e /usr/lib64/libvulkan.so.1 ] || [ -e /usr/lib/x86_64-linux-gnu/libvulkan.so.1 ]; then
    FLAVOR=ubuntu-vulkan-x64; EXTRA=
  else
    FLAVOR=ubuntu-x64; EXTRA=
  fi
  TAG=$(llama_tag "$FLAVOR")
  [ -n "$EXTRA" ] && EXTRA=cudart-llama-$TAG-bin-$FLAVOR.tar.gz
  echo "llama.cpp $TAG ($FLAVOR)"
  B=https://github.com/ggml-org/llama.cpp/releases/download/$TAG
  "${CURL[@]}" -o /tmp/llama.tgz "$B/llama-$TAG-bin-$FLAVOR.tar.gz"
  tar xzf /tmp/llama.tgz -C vendor/llama && rm /tmp/llama.tgz
  if [ -n "$EXTRA" ]; then
    "${CURL[@]}" -o /tmp/cudart.tgz "$B/$EXTRA"
    mkdir -p /tmp/cudart && tar xzf /tmp/cudart.tgz -C /tmp/cudart
    cp -n /tmp/cudart/*/* vendor/llama/llama-$TAG/ 2>/dev/null || true
    rm -rf /tmp/cudart /tmp/cudart.tgz
  fi
fi

# --- modèle ----------------------------------------------------------------
if [ "${STEPH_MODEL:-gemma}" = qwen ]; then
  REPO=bartowski/Qwen_Qwen3.5-2B-GGUF; FILE=Qwen_Qwen3.5-2B-Q4_K_M.gguf
else
  REPO=google/gemma-4-E2B-it-qat-q4_0-gguf; FILE=gemma-4-E2B_q4_0-it.gguf
fi
[ -s "$DATA/models/$FILE" ] || "${CURL[@]}" -C - -o "$DATA/models/$FILE" "https://huggingface.co/$REPO/resolve/main/$FILE"

# --- dépendances Python + voix ------------------------------------------------
uv sync -q
VOICE=${STEPH_VOICE_NAME:-fr_FR-siwis-medium}
[ -s "$DATA/voices/$VOICE.onnx" ] || uv run python -m piper.download_voices --download-dir "$DATA/voices" "$VOICE"

# --- commande steph ------------------------------------------------------------
uv tool install -e . -q --force
echo "Installé. Lance : steph"
