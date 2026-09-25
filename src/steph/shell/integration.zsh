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

# Question rapide : q pourquoi ça a planté ?
q() { noglob steph ask --once -- "$@" }
alias q='noglob q'
