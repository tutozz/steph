#!/usr/bin/env bash
# Installe tout ce qu'il faut à steph, sans droits root, dans cet ordre :
#   1. dépendances Python et voix Piper (≈ 230 Mo), puis la commande `steph`
#   2. steph parle : si on l'entend, le son fonctionne
#   3. llama.cpp (CUDA si carte NVIDIA, sinon Vulkan, sinon CPU ; x64 ou arm64)
#   4. le modèle GGUF de démarrage, avec une ligne de texte tous les 10 % et l'avancement
#      dit tous les 25 % : le modèle que le catalogue recommande (B9b, data/catalog.json :
#      steph-speak, petit modèle, publié sur Hugging Face) ; `steph setup` propose ensuite
#      le modèle de base si la machine est assez rapide. Gemma 4 E2B brut seulement sur
#      choix explicite (STEPH_MODEL=gemma), Qwen3.5 2B avec STEPH_MODEL=qwen. Sans modèle
#      publié au catalogue, retombe sur Gemma. --update remplace un ancien modèle v1.0.
#   5. `steph setup` (B7), seulement si un terminal est disponible (/dev/tty) : reprend
#      le choix du modèle et de la voix depuis le catalogue B4, recommandé selon le
#      matériel ; sans terminal, message clair et proposition au premier `steph` (B8b)
# --update : installe aussi une version plus récente de llama.cpp (appelé par `steph update`)
# --check  : dit ce qui serait installé ou mis à jour, sans rien modifier
# Messages en français ou en anglais selon la locale (LC_ALL, LC_MESSAGES, LANG).
set -euo pipefail

# ----------------------------------------------------------------- fonctions
is_french() {
  case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in fr*) return 0 ;; *) return 1 ;; esac
}

# msg "texte français" "English text"
msg() { if is_french; then printf '%s\n' "$1"; else printf '%s\n' "$2"; fi; }

# Charte graphique (src/steph/shell/style.sh) : aucun style hors terminal, avec
# NO_COLOR ou TERM=dumb. STEPH_STYLE vaut la profondeur de couleur de la sortie.
# shellcheck source=../src/steph/shell/style.sh
. "$(dirname "${BASH_SOURCE[0]}")/../src/steph/shell/style.sh"
STEPH_STYLE=none
# use_style_of FD : règle STEPH_STYLE pour ce descripteur. Pas de $(…) ici : dans
# une substitution, la sortie standard est un tuyau et [ -t 1 ] serait toujours faux.
use_style_of() {
  if [ -t "$1" ]; then STEPH_STYLE=$(__steph_color_depth); else STEPH_STYLE=none; fi
}

# styled ROLE TEXTE : strong (étape, erreur), accent (succès), muted (conseil),
# logo (« steph » et chevron, une ligne, seulement en couleur). Fond du terminal
# inconnu : jamais de couleur de texte sans fond (voir term_style.Style).
styled() {
  local depth=${STEPH_STYLE:-none} params text=${2:-}
  if [ "$depth" = none ]; then
    [ "$1" = logo ] || printf '%s\n' "$text"
    return 0
  fi
  case "$1" in
    strong) params=1 ;;
    accent|logo) params="$(__steph_fg "$depth" black);$(__steph_bg "$depth" lemon)" ;;
    *) params="$(__steph_fg "$depth" gray);$(__steph_bg "$depth" black)" ;;
  esac
  [ "$1" = logo ] && text=" steph $(__steph_chevron) "
  printf '\033[%sm%s\033[0m\n' "$params" "$text"
}

# smsg ROLE "texte français" "English text" : msg avec le style du rôle
smsg() { styled "$1" "$(msg "$2" "$3")"; }

# erreur sur stderr, en gras si stderr est un terminal
fail_msg() { local STEPH_STYLE; use_style_of 2; smsg strong "$1" "$2" >&2; }

lang_code() { if is_french; then echo fr; else echo en; fi; }

# Archive llama.cpp publiée pour cette machine ; échec sans sortie si aucune.
llama_flavor() { # OS ARCH GPU(nvidia|vulkan|none)
  local os=$1 arch=$2 gpu=$3
  case "$os/$arch" in
    Darwin/arm64) echo macos-arm64 ;;
    Darwin/x86_64) echo macos-x64 ;;
    Linux/x86_64|Linux/amd64)
      case "$gpu" in nvidia) echo ubuntu-cuda-12.8-x64 ;; vulkan) echo ubuntu-vulkan-x64 ;; *) echo ubuntu-x64 ;; esac ;;
    Linux/aarch64|Linux/arm64)
      case "$gpu" in nvidia) echo ubuntu-cuda-13.4-arm64 ;; vulkan) echo ubuntu-vulkan-arm64 ;; *) echo ubuntu-arm64 ;; esac ;;
    *) return 1 ;;
  esac
}

detect_gpu() {
  if command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then echo nvidia; return; fi
  local lib
  for lib in /usr/lib64/libvulkan.so.1 /usr/lib/x86_64-linux-gnu/libvulkan.so.1 /usr/lib/aarch64-linux-gnu/libvulkan.so.1; do
    [ -e "$lib" ] && { echo vulkan; return; }
  done
  echo none
}

# Taille totale à télécharger : gemma et qwen mesurés en B8a (modèle, llama.cpp, uv et
# Python, voix) ; steph = ces mesures moins Gemma (3,3 Go) plus le petit modèle (0,2 Go),
# estimé, pas mesuré.
plan_size() { # MODEL(steph|gemma|qwen) CUDART(1|vide)
  local fr en
  if [ "$1" = steph ]; then
    if [ -n "$2" ]; then fr="1,4 Go"; en="1.4 GB"; else fr="0,6 Go"; en="0.6 GB"; fi
  elif [ "$1" = qwen ]; then
    if [ -n "$2" ]; then fr="2,5 Go"; en="2.5 GB"; else fr="1,7 Go"; en="1.7 GB"; fi
  else
    if [ -n "$2" ]; then fr="4,4 Go"; en="4.4 GB"; else fr="3,6 Go"; en="3.6 GB"; fi
  fi
  smsg strong "steph : environ $fr à télécharger. La voix d'abord, puis llama.cpp et le modèle." \
      "steph: about $en to download. The voice first, then llama.cpp and the model."
}

# Après l'installation : steph est-il trouvable ? Sinon, chemin absolu et ligne exacte.
path_advice() { # BIN_DIR
  local bin=$1 rc
  # PATH du terminal de la personne, pas celui de l'installeur (qui a ajouté ~/.local/bin)
  if PATH="${STEPH_USER_PATH:-$PATH}" command -v steph >/dev/null 2>&1; then return 0; fi
  # le tilde est affiché tel quel : c'est ce que la personne tape
  # shellcheck disable=SC2088
  case "$(basename "${SHELL:-sh}")" in
    zsh) rc="~/.zshrc" ;;
    bash) rc="~/.bashrc" ;;
    fish) rc="~/.config/fish/config.fish" ;;
    *) rc="~/.profile" ;;
  esac
  smsg strong "La commande steph n'est pas encore dans le PATH de ce terminal." \
      "The steph command is not yet on this terminal's PATH."
  msg "Lancez-la par son chemin complet : $bin/steph" \
      "Run it by its full path: $bin/steph"
  msg "Ou ajoutez cette ligne à $rc, puis ouvrez un nouveau terminal :" \
      "Or add this line to $rc, then open a new terminal:"
  # shellcheck disable=SC2088
  if [ "$rc" = "~/.config/fish/config.fish" ]; then
    echo "fish_add_path \"$bin\""
  else
    echo "export PATH=\"$bin:\$PATH\""
  fi
}

# steph parle pendant l'installation (voix coupée : STEPH_TTS_ENABLED=0).
speak() { uv run -q steph say "$1" >/dev/null 2>&1 || true; }

# B7 : enchaîne sur `steph setup` à la fin d'une installation neuve. `setup.py` (B8b)
# porte lui-même toute la détection de terminal (/dev/tty) : sans terminal (curl | sh,
# cron, CI), il affiche un message clair et n'écrit rien, puis se représente au premier
# `steph` (should_run_first_setup). `|| true` : un setup refusé ou interrompu ne doit
# jamais faire échouer une installation par ailleurs réussie.
maybe_run_setup() { uv run -q steph setup || true; }

# Fixe MODEL_CHOICE (steph|gemma|qwen|keep), REPO, FILE et SHA. Le catalogue répond
# « dépôt fichier sha256 », « keep » (mise à jour : le modèle en place reste) ou rien.
resolve_model() {
  MODEL_CHOICE=gemma SHA=
  REPO=google/gemma-4-E2B-it-qat-q4_0-gguf; FILE=gemma-4-E2B_q4_0-it.gguf
  case "${STEPH_MODEL:-}" in
    qwen) MODEL_CHOICE=qwen; REPO=bartowski/Qwen_Qwen3.5-2B-GGUF; FILE=Qwen_Qwen3.5-2B-Q4_K_M.gguf; return 0 ;;
    gemma) return 0 ;;
  esac
  local pick flag=""
  [ "$MODE" = install ] || flag="--update"
  # src/steph/catalog.py n'importe que la bibliothèque standard : pas besoin du venv (--check)
  pick=$(PYTHONPATH="$PWD/src" uv run --no-project -q python -m steph.catalog install-model $flag 2>/dev/null || true)
  case "$pick" in
    keep) MODEL_CHOICE=keep ;;
    "") ;;
    *) MODEL_CHOICE=steph; set -- $pick; REPO=$1; FILE=$2; SHA=${3:-} ;;
  esac
}

llama_tag() {
  "${CURL[@]}" -s "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=30" |
    uv run --no-project -q python -c '
import json, sys
flavor = sys.argv[1]
for r in json.load(sys.stdin):
    t = r["tag_name"]
    if any(a["name"] == f"llama-{t}-bin-{flavor}.tar.gz" for a in r["assets"]):
        print(t); break
else:
    sys.exit(f"llama.cpp : aucune release ne publie le binaire {flavor}")
' "$1"
}

fetch() { # LABEL URL DEST [--speak]
  # ${4:-} sans guillemets : absent, il ne doit laisser aucun argument vide (bash 3.2, set -u)
  # shellcheck disable=SC2086
  uv run -q python -m steph.fetch --lang "$(lang_code)" --label "$1" ${4:-} "$2" "$3"
}

# Le binaire de ce dossier s'exécute-t-il ? Les archives Linux de ggml-org visent
# une glibc récente (Ubuntu 24.04, 2.38) : sur Debian 12 ou Ubuntu 22.04 il ne démarre pas.
llama_usable() { # DIR
  "$1/llama-server" --version >/dev/null 2>&1
}

# Construit llama-server depuis les sources de la release $1 et le pose dans $2.
# Binaires statiques ; CUDA si nvcc est présent, sinon CPU.
llama_build_source() { # TAG DIR
  local TAG=$1 DEST=$2 SRC cuda=OFF
  SRC=$(mktemp -d)
  fetch "llama.cpp (sources)" "https://github.com/ggml-org/llama.cpp/archive/refs/tags/$TAG.tar.gz" "$SRC/src.tgz" || return 1
  tar xzf "$SRC/src.tgz" -C "$SRC" || return 1
  command -v nvcc >/dev/null && [ "$GPU" = nvidia ] && cuda=ON
  cmake -S "$SRC/llama.cpp-$TAG" -B "$SRC/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
    -DGGML_CUDA=$cuda -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF >"$SRC/cmake.log" 2>&1 &&
    cmake --build "$SRC/build" --target llama-server llama-bench -j "$(nproc 2>/dev/null || echo 2)" >>"$SRC/cmake.log" 2>&1 || {
      tail -n 15 "$SRC/cmake.log" >&2
      rm -rf "$SRC"
      return 1
    }
  # llama-bench sert à steph pour détecter le GPU ; les fichiers de l'archive inutilisable partent
  rm -rf "$DEST" && mkdir -p "$DEST" && cp "$SRC/build/bin/llama-server" "$SRC/build/bin/llama-bench" "$DEST/"
  rm -rf "$SRC"
}

# Vérifie que llama-server s'exécute ; sinon le construit depuis les sources, ou le dit.
llama_ensure_usable() { # TAG DIR
  local TAG=$1 D=$2
  llama_usable "$D" && return 0
  if [ "$OS" = Linux ] && command -v cmake >/dev/null && command -v c++ >/dev/null; then
    smsg strong "llama.cpp : le binaire publié ne démarre pas (glibc trop ancienne). Construction depuis les sources, quelques minutes." \
                "llama.cpp: the published binary does not start (glibc too old). Building from source, a few minutes."
    llama_build_source "$TAG" "$D" && llama_usable "$D" && return 0
    fail_msg "llama.cpp : la construction depuis les sources a échoué. steph n'est pas utilisable." \
             "llama.cpp: the build from source failed. steph is not usable."
    return 1
  fi
  fail_msg "llama.cpp : le binaire publié ne démarre pas (glibc trop ancienne). Installez cmake et un compilateur C++ (paquets cmake et g++), puis relancez l'installation. steph n'est pas utilisable." \
           "llama.cpp: the published binary does not start (glibc too old). Install cmake and a C++ compiler (packages cmake and g++), then run the installer again. steph is not usable."
  return 1
}

# Télécharge la release $1 dans vendor/llama.new puis remplace vendor/llama :
# un téléchargement interrompu laisse l'ancienne version en place.
install_llama() {
  local TAG=$1 NEW=vendor/llama.new TMP
  local B=https://github.com/ggml-org/llama.cpp/releases/download/$TAG
  TMP=$(mktemp -d)
  smsg strong "llama.cpp $TAG ($FLAVOR)" "llama.cpp $TAG ($FLAVOR)"
  rm -rf "$NEW" && mkdir -p "$NEW"
  fetch llama.cpp "$B/llama-$TAG-bin-$FLAVOR.tar.gz" "$TMP/llama.tgz"
  tar xzf "$TMP/llama.tgz" -C "$NEW"
  if [ "$OS" = Darwin ]; then
    # les bibliothèques peuvent être rangées à part : on les met à côté du binaire
    D=$(dirname "$(ls "$NEW"/*/llama-server "$NEW"/*/*/llama-server 2>/dev/null | head -1)")
    [ "$(basename "$D")" = bin ] && mv "$D"/* "$D/.." 2>/dev/null || true
    xattr -dr com.apple.quarantine "$NEW" 2>/dev/null || true
  fi
  # testé avant cudart : un binaire qui ne démarre pas est reconstruit, inutile de télécharger CUDA
  local D=$NEW/llama-$TAG built=""
  llama_usable "$D" || { llama_ensure_usable "$TAG" "$D" || { rm -rf "$TMP" "$NEW"; return 1; }; built=1; }
  if [ -n "$CUDART" ] && [ -z "$built" ]; then
    fetch "CUDA" "$B/cudart-llama-$TAG-bin-$FLAVOR.tar.gz" "$TMP/cudart.tgz"
    mkdir -p "$TMP/cudart" && tar xzf "$TMP/cudart.tgz" -C "$TMP/cudart"
    cp -n "$TMP"/cudart/*/* "$NEW/llama-$TAG/" 2>/dev/null || true
  fi
  rm -rf "$TMP"
  echo "$TAG" > "$NEW/TAG"
  rm -rf vendor/llama && mv "$NEW" vendor/llama
}

section_llama() {
  local HAS_VENDOR TAG CURRENT
  HAS_VENDOR=$(ls vendor/llama/llama-*/llama-server 2>/dev/null | head -1 || true)
  if [ "$OS" = Darwin ] && command -v brew >/dev/null && brew list llama.cpp >/dev/null 2>&1; then
    # llama.cpp géré par Homebrew (Metal inclus)
    if [ "$MODE" != install ]; then
      # --check ne doit rien modifier, pas même l'index Homebrew
      if [ "$MODE" = check ]; then export HOMEBREW_NO_AUTO_UPDATE=1; fi
      if [ -z "$(brew outdated --quiet llama.cpp)" ]; then
        msg "llama.cpp : à jour (Homebrew)" "llama.cpp: up to date (Homebrew)"
      elif [ "$MODE" = check ]; then
        msg "llama.cpp : mise à jour Homebrew disponible" "llama.cpp: Homebrew update available"
      else
        brew upgrade llama.cpp
      fi
    fi
  elif [ "$OS" = Darwin ] && [ -z "$HAS_VENDOR" ] && command -v llama-server >/dev/null; then
    # installé à la main hors Homebrew : on n'y touche pas
    [ "$MODE" = install ] || msg "llama.cpp : $(command -v llama-server), installé à la main, non mis à jour" \
                                 "llama.cpp: $(command -v llama-server), installed by hand, not updated"
  elif [ "$OS" = Darwin ] && [ -z "$HAS_VENDOR" ] && command -v brew >/dev/null; then
    if [ "$MODE" = check ]; then
      msg "llama.cpp : absent, à installer par Homebrew" "llama.cpp: missing, to install with Homebrew"
    else
      brew install -q llama.cpp
    fi
  elif [ -z "$HAS_VENDOR" ] || [ "$MODE" != install ]; then
    TAG=$(llama_tag "$FLAVOR")
    CURRENT=$(cat vendor/llama/TAG 2>/dev/null || true)
    if [ -n "$HAS_VENDOR" ] && [ "$CURRENT" = "$TAG" ]; then
      msg "llama.cpp : à jour ($TAG)" "llama.cpp: up to date ($TAG)"
    elif [ "$MODE" = check ]; then
      msg "llama.cpp : $TAG à installer (actuel : ${CURRENT:-inconnu})" \
          "llama.cpp: $TAG to install (current: ${CURRENT:-unknown})"
    else
      install_llama "$TAG" || exit 1
    fi
  fi
}

# ----------------------------------------------------------------- déroulé
main() {
  MODE=install
  case "${1:-}" in
    "") ;;
    --update) MODE=update ;;
    --check) MODE=check ;;
    *) echo "usage : $0 [--update|--check]" >&2; exit 2 ;;
  esac
  cd "$(dirname "$0")/.."
  use_style_of 1
  [ "$MODE" = install ] && styled logo
  DATA="${XDG_DATA_HOME:-$HOME/.local/share}/steph"
  CURL=(curl -q -fL --retry 3)   # -q : ignore ~/.curlrc
  OS=$(uname -s)

  local tool
  for tool in uv curl tar; do
    command -v "$tool" >/dev/null || { fail_msg "steph : $tool est requis." "steph: $tool is required."; exit 1; }
  done
  GPU=none
  [ "$OS" = Linux ] && GPU=$(detect_gpu)
  FLAVOR=$(llama_flavor "$OS" "$(uname -m)" "$GPU") || {
    fail_msg "steph : machine non prise en charge ($OS $(uname -m)). Linux ou macOS, x86_64 ou arm64." \
             "steph: unsupported machine ($OS $(uname -m)). Linux or macOS, x86_64 or arm64."
    exit 1
  }
  CUDART=$([ "$GPU" = nvidia ] && echo 1 || true)

  resolve_model
  VOICE=${STEPH_VOICE_NAME:-fr_FR-siwis-medium}
  # la voix installée ici est celle que `steph say` doit utiliser, même hors défaut
  export STEPH_VOICE="$DATA/voices/$VOICE.onnx"

  if [ "$MODE" = check ]; then
    section_llama
    if [ "$MODEL_CHOICE" = keep ]; then msg "modèle : celui de la configuration est conservé" "model: the configured one is kept"
    elif [ -s "$DATA/models/$FILE" ]; then msg "modèle : $FILE présent" "model: $FILE present"
    else msg "modèle : $FILE à télécharger" "model: $FILE to download"; fi
    if [ -s "$DATA/voices/$VOICE.onnx" ]; then msg "voix : $VOICE présente" "voice: $VOICE present"
    else msg "voix : $VOICE à télécharger" "voice: $VOICE to download"; fi
    exit 0
  fi

  mkdir -p "$DATA/models" "$DATA/voices" vendor/llama
  [ "$MODE" = install ] && plan_size "$MODEL_CHOICE" "$CUDART"

  # --- 1. dépendances Python, voix, commande steph -------------------------------
  smsg strong "Voix : installation (environ 230 Mo)." "Voice: installing (about 230 MB)."
  uv sync -q
  if [ ! -s "$DATA/voices/$VOICE.onnx" ]; then
    uv run -q python -m piper.download_voices --download-dir "$DATA/voices" "$VOICE" >/dev/null 2>&1 || {
      fail_msg "Voix : téléchargement impossible ($VOICE). Relancez l'installation." \
               "Voice: download failed ($VOICE). Run the installer again."
      exit 1
    }
  fi
  uv tool install -e . -q --force
  BIN=$(uv tool dir --bin 2>/dev/null || echo "$HOME/.local/bin")

  # --- 2. premier son ------------------------------------------------------------
  if [ "$MODE" = install ]; then
    local said
    if said=$(uv run -q steph say "$(msg "Installation de steph. Si vous m'entendez, le son fonctionne. Je télécharge maintenant le modèle de langage." \
                                        "Installing steph. If you can hear me, sound works. I am now downloading the language model.")" 2>&1); then
      msg "steph vient de parler. Si vous n'avez rien entendu, vérifiez le volume ; tout reste affiché en texte." \
          "steph just spoke. If you heard nothing, check the volume; everything is also shown as text."
    else
      # steph say explique pourquoi aucun son ne sortira (aucun lecteur audio)
      printf '%s\n' "$said" >&2
    fi
    if [ "$OS" = Darwin ] && ! command -v sox >/dev/null; then
      smsg muted "Conseil : brew install sox rend la voix plus réactive." "Tip: brew install sox makes the voice more responsive."
    fi
  fi

  # --- 3. llama.cpp ----------------------------------------------------------------
  section_llama

  # --- 4. modèle -------------------------------------------------------------------
  if [ "$MODEL_CHOICE" = keep ]; then
    msg "modèle : celui de la configuration est conservé" "model: the configured one is kept"
  elif [ ! -s "$DATA/models/$FILE" ]; then
    fetch "$(msg Modèle Model)" "https://huggingface.co/$REPO/resolve/main/$FILE" "$DATA/models/$FILE" \
      "$([ "$MODE" = install ] && echo --speak) ${SHA:+--sha256 $SHA}"
  elif [ "$MODE" != install ]; then
    msg "modèle : $FILE présent" "model: $FILE present"
  fi
  # ancien modèle v1.0 : config.toml pointe vers le fichier qui le remplace (l'ancien reste sur le disque)
  [ "$MODE" = update ] && { uv run -q python -m steph.catalog migrate || true; }
  # sans `steph setup` (pas de terminal, refus), config.toml doit quand même désigner le modèle téléchargé
  [ "$MODEL_CHOICE" = steph ] && { uv run -q python -m steph.catalog adopt "$FILE" || true; }

  # --- fin -------------------------------------------------------------------------
  smsg accent "steph est installé." "steph is installed."
  if PATH="${STEPH_USER_PATH:-$PATH}" command -v steph >/dev/null 2>&1; then
    smsg strong "Lancez : steph" "Run: steph"
  else
    path_advice "$BIN"
  fi
  smsg muted "Réglages : steph setup. Désinstallation : steph uninstall." "Settings: steph setup. Uninstall: steph uninstall."
  [ "$MODE" = install ] && speak "$(msg "steph est prêt. Lancez steph dans un terminal." "steph is ready. Run steph in a terminal.")"
  [ "$MODE" = install ] && maybe_run_setup
  return 0
}

# exécuté (et non sourcé par les tests) : on installe
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
