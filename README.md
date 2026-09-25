# steph — terminal parlant

Un shell qui parle, pour les personnes malvoyantes. `steph` relance ton shell
(zsh ou bash, avec ta config habituelle) et écoute tout ce qui passe. Au lieu
de lire tout le texte à voix haute, il dit **l'essentiel, en une phrase** :

- `ls /usr` → lit la sortie telle quelle (courte) ;
- `cat /nope` → « Erreur 1 : cat: /nope: Aucun fichier ou dossier de ce nom » ;
- `npm run build` qui échoue → « Erreur TypeScript : la propriété titel n'existe pas, utilisez title. » ;
- `apt upgrade` → « En cours : mise à jour des paquets. » … « 35 pour cent, décompression de vim-common. » … « Terminé en 1 minute 24. 12 paquets mis à jour. » ;
- une question `[O/n]` → « Question : il est nécessaire de prendre 24 Mo. Souhaitez-vous continuer ? oui ou non, oui par défaut » ;
- `ssh`, `python`, `psql`… → lit la réponse à chaque commande tapée dedans.

Tout tourne **en local** : un petit LLM (Gemma 4 E2B via llama.cpp, sur GPU) et
la synthèse vocale Piper (voix française). Rien ne sort de la machine.

## Installation

```sh
./scripts/install.sh      # llama.cpp + modèle (~3 Go) + voix + commande steph
steph                     # lance le terminal parlant
```

Prérequis : `uv` ([installation](https://docs.astral.sh/uv/)).

**Linux** : PipeWire ou PulseAudio (`paplay`). Une carte NVIDIA est utilisée si
elle est présente (4 Go suffisent), sinon Vulkan, sinon CPU.

**macOS** (Apple Silicon ou Intel) :

```sh
brew install uv llama.cpp sox   # sox : voix plus réactive (sinon afplay, intégré)
./scripts/install.sh
steph
```

- Le modèle tourne sur le GPU via Metal (llama.cpp de Homebrew, ou le binaire
  officiel si Homebrew est absent).
- Sur Mac, les touches F7 à F10 sont des touches multimédia : il faut appuyer
  sur **fn** en même temps, ou activer « Utiliser F1, F2… comme touches de
  fonction standard » (Réglages → Clavier). On peut aussi choisir d'autres
  touches dans `config.toml`.
- La fenêtre de questions (F7) s'ouvre dans Terminal.app, ou dans iTerm si
  `steph` tourne dans iTerm.
- Si Piper n'est pas disponible, `steph` se rabat sur la voix système `say`
  (voix « Thomas », à changer avec `STEPH_MAC_VOICE`).
- Détection des questions : `ps -o wchan` (état `ttyin`) remplace `/proc`.

## Touches et commandes

| Touche / commande | Effet |
|---|---|
| **F7** | ouvre la fenêtre de questions (2e terminal) |
| **F8** | silence immédiat |
| **F9** | répète la dernière annonce |
| **F10** | explication détaillée de la dernière commande |
| `q pourquoi ça a planté ?` | question rapide, sans quitter le shell |
| `steph ask` | fenêtre de questions (dans n'importe quel terminal) |
| `steph ctl stop\|repeat\|details\|status\|history` | contrôle à distance de la session |
| `steph say "texte"` | tester la voix |
| `steph server status\|stop` | le modèle local |

Les questions portent sur **tout l'historique de la session** : commandes,
codes de retour et sorties. Pas besoin de recopier quoi que ce soit.

## Comment ça marche

```
clavier ──► proxy PTY ──► ton shell (zsh/bash + marqueurs)
                │  ▲
   sortie ◄─────┘  │ marqueurs invisibles : début de commande, fin + code de retour
                ▼
          nettoyeur (ANSI, \r, barres de progression, ligne de statut d'apt)
                ▼
          narrateur ── règles déterministes (instantané) ──┐
                │                                          ├──► Piper ──► haut-parleur
                └── LLM local (résumés, étapes, Q&R) ──────┘
```

- **Déterministe d'abord.** Sortie vide → « OK » ; sortie courte → lue telle
  quelle ; `cd` → « Dossier tmp » ; code 127 → « Commande introuvable » ;
  pourcentages et étapes connues (apt, dnf, pip, git, docker, cargo, make…)
  extraits par expressions régulières. Le LLM ne sert que pour résumer une
  sortie longue ou expliquer une erreur.
- **Parler tôt.** La réponse du LLM est lue phrase par phrase pendant qu'elle
  se génère. Pour une commande longue, « Terminé en 32 secondes » est dit
  immédiatement pendant que le résumé se calcule.
- **Savoir quand le programme attend l'utilisateur.** `steph` regarde dans
  `/proc/<pid>/syscall` si le programme au premier plan est bloqué en lecture
  sur le terminal. Il distingue ainsi une vraie question d'une commande tapée
  à l'avance.
- **Questions rapides grâce au cache.** L'historique est construit en « ajout
  seul » et pré-calculé pendant que le GPU est libre (préchauffage annulable).
  Une question ne coûte donc que le calcul de ses propres mots : environ 1 s
  au lieu de 20 à 30 s.
- **Robuste.** Si le modèle tombe, `steph` le relance et utilise un résumé
  déterministe en attendant.

## Choix du modèle (mesures sur NVIDIA T600 4 Go)

| Modèle | Latence moyenne d'un résumé | Qualité |
|---|---|---|
| Qwen3.5 0.8B | 0,6 s | invente trop |
| LFM2.5 1.2B | 1,1 s | style télégraphique, peu utile |
| Qwen3.5 2B | 1,1 s | correct, quelques erreurs |
| **Gemma 4 E2B** (défaut) | 1,5 s | factuel, meilleur en Q&R |
| granite 4.2 3B | 2,8 s | précis, laisse fuiter `</think>` |
| Qwen3.5 4B | 3,2 s | le meilleur, trop lent |

Benchmark reproductible : `bench/bench.py` (fixtures réelles dans `bench/`).

## Configuration

Voir `config.example.toml` → `~/.config/steph/config.toml`.

## Tests

La CI GitHub Actions (`.github/workflows/ci.yml`) lance les tests sur Ubuntu
et macOS, avec zsh et bash (le bash 3.2 de macOS compris), ainsi qu'un test
de bout en bout du LLM sur Mac avec llama.cpp de Homebrew.

```sh
uv run pytest tests               # unitaires (nettoyeur, marqueurs, étapes)
uv run python tests/e2e.py basic  # bout en bout, voix coupée, journal de parole
#   scénarios : basic long prompt repl subshell ask keys real typeahead
```

Journal : `$XDG_RUNTIME_DIR/steph/steph.log` et `llama-server.log`.

## Limites connues

- Les applications plein écran (vim, htop, less) ne sont pas lues : `steph`
  annonce seulement qu'elles sont ouvertes.
- La touche Entrée tapée à l'avance est bien gérée, mais pas les flèches dans
  une ligne en cours d'édition, dont le filtrage reste approximatif.
- Le petit modèle se trompe parfois dans les comptes, par exemple « 50 nombres »
  au lieu de 60. F10 et les questions donnent plus de détails.
