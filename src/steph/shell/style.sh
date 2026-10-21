# Charte graphique pour les scripts shell (sh, bash 3.2+, zsh) : copie de
# src/steph/term_style.py, parité vérifiée par tests/test_term_style.py.
# Le test « la sortie est-elle un terminal » reste à l'appelant ([ -t 1 ]).

# truecolor | 256 | 16 | none
__steph_color_depth() {
  if [ -n "${NO_COLOR:-}" ]; then printf none; return; fi
  case "${TERM:-}" in ''|dumb) printf none; return ;; esac
  case "${COLORTERM:-}" in truecolor|24bit) printf truecolor; return ;; esac
  case "$TERM" in *256color*) printf 256 ;; *) printf 16 ;; esac
}

# __steph_fg DEPTH NAME : paramètres SGR de la couleur de texte (sans ESC[ ni m)
__steph_fg() {
  case "$1/$2" in
    truecolor/black) printf '38;2;11;11;11' ;;
    truecolor/offwhite) printf '38;2;244;244;240' ;;
    truecolor/lemon) printf '38;2;226;255;59' ;;
    truecolor/gray) printf '38;2;138;138;133' ;;
    256/black) printf '38;5;232' ;;
    256/offwhite) printf '38;5;255' ;;
    256/lemon) printf '38;5;191' ;;
    256/gray) printf '38;5;245' ;;
    */black) printf 30 ;;
    */offwhite) printf 97 ;;
    */lemon) printf 93 ;;
    */gray) printf 90 ;;
  esac
}

# __steph_bg DEPTH NAME : paramètres SGR de la couleur de fond
__steph_bg() {
  case "$1" in
    truecolor|256) __steph_fg "$1" "$2" | sed 's/^38/48/' ;;
    *) printf '%s' "$(( $(__steph_fg "$1" "$2") + 10 ))" ;;
  esac
}

# __steph_prompt_segment OPEN CLOSE KEY : indicateur de prompt. Segment citron
# (chevron et touche du menu en noir) puis pointe citron sur le fond du terminal.
# OPEN/CLOSE encadrent les séquences invisibles (zsh : %{ %}, bash : \[ \]).
# Pointe : U+E0B0 (police Powerline ou Nerd Font) ; STEPH_PROMPT_TIP la remplace,
# vide pour la retirer. Sans couleur : « › F6 », sans séquence ni pointe.
__steph_prompt_segment() {
  __steph_d=$(__steph_color_depth)
  __steph_c=$(__steph_chevron)
  if [ "$__steph_d" = none ]; then
    printf '%s %s ' "$__steph_c" "$3"
    return
  fi
  case "$__steph_c" in '>') __steph_t= ;; *) __steph_t=$(printf '\356\202\260') ;; esac
  __steph_t=${STEPH_PROMPT_TIP-$__steph_t}
  __steph_e=$(printf '\033')
  printf '%s%s[0;%s;%sm%s %s %s ' "$1" "$__steph_e" "$(__steph_bg "$__steph_d" lemon)" \
    "$(__steph_fg "$__steph_d" black)" "$2" "$__steph_c" "$3"
  printf '%s%s[0;%sm%s%s%s%s[0m%s ' "$1" "$__steph_e" "$(__steph_fg "$__steph_d" lemon)" "$2" \
    "$__steph_t" "$1" "$__steph_e" "$2"
  unset __steph_d __steph_c __steph_t __steph_e
}

# › (U+203A) en UTF-8, > sinon ou sur un terminal minimal
__steph_chevron() {
  case "${TERM:-}" in dumb) printf '>'; return ;; esac
  case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
    *[Uu][Tt][Ff]-8*|*[Uu][Tt][Ff]8*) printf '\342\200\272' ;;
    *) printf '>' ;;
  esac
}
