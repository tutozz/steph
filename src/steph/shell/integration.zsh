# Marqueurs OSC 6973 lus (et masqués) par steph.
#   C;<cmd base64>          juste avant l'exécution d'une commande
#   D;<code>;<cwd base64>   au retour au prompt
zmodload zsh/datetime 2>/dev/null
__steph_b64() { print -rn -- "$1" | base64 | tr -d "\n" }
__steph_preexec() { print -rn -- $'\e]6973;C;'"$(__steph_b64 "$1")"$'\a' }
__steph_precmd() {
  local ret=$?
  print -rn -- $'\e]6973;D;'"$ret;$(__steph_b64 "$PWD")"$'\a'
}
autoload -Uz add-zsh-hook
add-zsh-hook preexec __steph_preexec
precmd_functions=(__steph_precmd ${precmd_functions:#__steph_precmd})

# Indicateur de prompt (segment citron de la charte, voir style.sh) : inséré
# en tête de la DERNIÈRE ligne du prompt (pas en tête de PROMPT, qui peut être
# multiligne : starship avec add_newline, par exemple). PROMPT peut être une
# expression à évaluer à chaque tour (starship, p10k… avec PROMPT_SUBST) : on
# la sauvegarde et on l'évalue nous-mêmes dans le wrapper, pour rester exacts
# même quand son rendu change de forme d'un tour à l'autre. Ajouté en DERNIER
# dans precmd_functions, pour agir après les thèmes qui réécrivent PROMPT.
source "${${(%):-%x}:A:h}/style.sh"
__steph_tag="$(__steph_prompt_segment '%{' '%}' "$STEPH_MENU_KEY")"
__steph_prompt_insert() {
  local rendered="$1" tag="$__steph_tag"
  if [[ "$rendered" == *$'\n'* ]]; then
    print -rn -- "${rendered%$'\n'*}"$'\n'"${tag}${rendered##*$'\n'}"
  else
    print -rn -- "${tag}${rendered}"
  fi
}
__steph_prompt_wrap() { __steph_prompt_insert "${(e)__steph_orig_prompt}" }
__steph_prompt_tag() {
  case "$PROMPT" in
    '$(__steph_prompt_wrap)') return ;;             # thème dynamique : déjà posé
    *"$__steph_tag"*) return ;;                       # texte statique : déjà posé
    *'$('*|*'`'*)
      # expression à réévaluer à chaque tour (starship, p10k…)
      __steph_orig_prompt="$PROMPT"
      PROMPT='$(__steph_prompt_wrap)'
      ;;
    *)
      PROMPT="$(__steph_prompt_insert "$PROMPT")"
      ;;
  esac
}
precmd_functions=(${precmd_functions:#__steph_prompt_tag} __steph_prompt_tag)

# Question rapide : q pourquoi ça a planté ?
q() { noglob steph ask --once -- "$@" }
alias q='noglob q'
