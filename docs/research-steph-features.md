# Recherche : fonctionnalités indispensables pour steph

Tâche H1 du journal de mission interne (non publié). Rédigé le 2026-09-27. Entrée de H2 (`docs/research-retraining.md`).

Public visé : personnes malvoyantes ou aveugles qui travaillent en terminal (développeurs, administrateurs
système, étudiants), sous Linux et macOS.

## Ce que steph sait déjà faire

| Domaine | Existant | Fichier |
|---|---|---|
| Résumé d'une sortie longue | LLM, 15 mots, style télégraphique, français | `src/steph/prompts.py:5` |
| Sorties spécialisées | digest réseau, disques, lspci, listes | `src/steph/digest.py:27` |
| Progression | pourcentages et étapes par regex (apt, pip, git, docker, cargo), sinon LLM | `src/steph/narrator.py:574` |
| Questions `[O/n]`, mots de passe | détection par `/proc/<pid>/syscall` ou `ps -o wchan` | `src/steph/narrator.py:649` |
| REPL et ssh | lecture de chaque réponse, résumé si longue | `src/steph/narrator.py:684` |
| Plein écran (vim, less, top) | annonce seule : « vim en plein écran » | `src/steph/narrator.py:579` |
| Touches | F6 menu, F7 questions, F8 silence, F9 répéter, F10 détail, Maj+F5 à F8 relecture ligne | `README.fr.md` |
| Règles par commande | mute, mute-all, verbatim, summary | `config.example.toml` |
| Voix | Piper siwis, prononciation des sigles, français seul | `src/steph/pronounce.py` |

## Ce que le modèle affiné a appris

Mesuré sur `bench/matrix/finetune/labeled/train.jsonl` (3 538 exemples) :

| Constat | Valeur | Conséquence |
|---|---|---|
| Tâches apprises | **une seule** : le résumé (un seul prompt système, `TRAIN_SYSTEM`) | F10, questions, points d'étape, annonce de début : jamais appris |
| Format d'entrée | `Commande / Statut / Durée / Sortie`, sortie passée par `digest` ou `compact` | tout nouveau digest change l'entrée |
| Langue de réponse | français seul | anglais : réentraînement complet |
| Longueur des réponses | 6,7 mots en moyenne, 25 au plus | un résumé à plusieurs erreurs sort du format |
| Tests (pytest, jest, cargo test, go test) | 1 exemple pytest, 0 pour les autres | résultats de tests hors distribution |
| `git diff` / `git status` / `git log` | 29 / 62 / 60 | diff couvert à la marge |
| Traces Python | 132 | couvertes |
| Sorties à 3 erreurs ou plus | 81 | multi-erreurs peu couvertes |
| kubectl, `-f` en flux, ssh | 0 / 7 / 3 | quasi absents |
| Écritures non latines | 0 | autres langues absentes |

## Classement

Légende de la colonne **Modèle** :

- **hors modèle** : touches, voix, sons, règles en code ; le modèle reçoit la même chose.
- **entrée changée** : nouveau type de sortie, nouveau digest, nouveau prompt, nouvelle langue ou nouveau mode de
  réponse. Détail à trancher par H2.

Effort : S (moins d'un jour), M (2 à 4 jours), L (une semaine ou plus).

### Les 10 premières, par valeur pour l'utilisateur

| # | Fonctionnalité | Problème réel résolu | Fréquence / gravité | Effort | Modèle | Classe |
|---|---|---|---|---|---|---|
| 1 | **Coexistence avec le lecteur d'écran** : parler par speech-dispatcher (Orca) ou VoiceOver, file commune, pas de double parole ; mode « steph résume, le lecteur lit » | Presque tout aveugle a déjà un lecteur actif ; deux voix en même temps rendent les deux inutilisables. Orca passe par speech-dispatcher et prend la priorité ([Arch](https://bbs.archlinux.org/viewtopic.php?id=268780), [Kicksecure](https://www.kicksecure.com/wiki/Orca)) | chaque session, bloquant | M | hors modèle | indispensable |
| 2 | **Erreurs multiples** : « 7 erreurs, 3 fichiers ; première : main.c ligne 12 » puis touche « erreur suivante / précédente » | Les développeurs aveugles se perdent dans la structure des erreurs et ont besoin d'aide pour naviguer ([ToPSen, 2025](https://arxiv.org/pdf/2505.22414)) ; Emacspeak a `next-error` parlé ([manuel](https://tvraman.github.io/emacspeak/manual/emacspeak_002dspeak.html)) | chaque build raté, forte | M | **entrée changée** : liste d'erreurs parsée (gcc, clang, tsc, rustc, eslint) en entrée, réponse « compte + première » ; hors format 15 mots | indispensable |
| 3 | **F10, questions, étapes et annonce de début sur le petit modèle** | Le modèle affiné ne connaît que le résumé ; s'il remplace Gemma, F10 et les questions régressent. Les questions sont la fonction phare du site | chaque question, forte | M | **entrée changée** : 4 prompts jamais appris (`DETAILS`, `QA`, `PROGRESS`, `START`) | indispensable |
| 4 | **Plein écran lu à la demande** : `less`/`man` page par page, instantané résumé de `top`/`htop`, mode et ligne courante de `vim` | Limite connue de steph ; VoiceOver lit mal vim ([AppleVis](https://www.applevis.com/forum/macos-mac-apps/how-can-you-even-use-terminal-daily-macos-voiceover-major-bugs-vim)) ; tdsr compare l'écran avant et après chaque touche ([tdsr](https://github.com/tspivey/tdsr)) | quotidienne (man, less, git log), forte | L | **entrée changée** : nouveau type « instantané d'écran 80x24 » | indispensable |
| 5 | **Menus à flèches et invites riches** : dire l'option en surbrillance (inquirer, fzf, npm init, gh, dialog, whiptail) | Les invites riches sont illisibles au lecteur d'écran ([GitHub CLI](https://github.blog/engineering/user-experience/building-a-more-accessible-github-cli/)) ; les invites sont « les interactions les plus critiques » ([claude-code #70425](https://github.com/anthropics/claude-code/issues/70425)) ; Fenrir suit la surbrillance ([manuel](https://manpages.ubuntu.com/manpages/bionic/man1/fenrir.1.html)) | hebdomadaire, bloquante | M | hors modèle (diff d'écran, attribut inverse) | indispensable |
| 6 | **Résultats de tests** : « 142 réussis, 2 échoués : test_login, test_logout » puis cause du premier échec | Les tests sont le retour principal d'un développeur aveugle, qui préfère `printf` et interpréteur au débogueur ([CHI 2021](https://research.google/pubs/accessibility-of-command-line-interfaces/)) | plusieurs fois par jour, forte | M | **entrée changée** : digest de tests (pytest, jest, vitest, cargo, go) ; 1 seul exemple au corpus | indispensable |
| 7 | **Sons de statut** : succès, échec, question en attente, commande longue finie | Emacspeak double la parole d'icônes sonores ([manuel](https://tvraman.github.io/emacspeak/manual/Auditory-Icons.html)) ; VS Code a `terminalCommandFailed` ([v1.89](https://code.visualstudio.com/updates/v1_89)) ; demande explicite d'earcons ([#70425](https://github.com/anthropics/claude-code/issues/70425)) | chaque commande, moyenne | S | hors modèle | indispensable |
| 8 | **Tableaux lus en « colonne : valeur »** en relecture, résumé des tableaux (`docker ps`, `kubectl get`, `ps`, `ls -l`) | Sans en-têtes ni bornes, l'utilisateur doit mémoriser les colonnes ([CHI 2021](https://dl.acm.org/doi/fullHtml/10.1145/3411764.3445544), repris par [216digital](https://216digital.com/can-a-command-line-be-accessible-by-design/)) ; Claude Code lit les tableaux en `Header: value` ([doc](https://code.claude.com/docs/en/accessibility)) | quotidienne (admins), forte | M | relecture : hors modèle ; résumé : **entrée changée** si le tableau passe en clé-valeur avant le modèle | indispensable |
| 9 | **Journaux en continu** (`tail -f`, `journalctl -f`, `docker logs -f`, `npm run dev`) : ne dire que les nouvelles erreurs et avertissements, compte périodique | Un admin suit des journaux sans fin ; aujourd'hui steph y applique le point d'étape générique | quotidienne (admins), moyenne | M | **entrée changée** : mode « flux » (fenêtre glissante, erreurs seules) ; 7 exemples au corpus | indispensable |
| 10 | **Anglais complet** : prompts, réponses, voix Piper anglaise, prononciation | NVDA domine hors Amérique du Nord, JAWS en Amérique du Nord ([WebAIM #10](https://webaim.org/projects/screenreadersurvey10/)) : le public est majoritairement non francophone | toute la cible anglophone, bloquante pour elle | L | **entrée changée** : nouvelle langue de réponse, prompts traduits ; réentraînement (tâche F1) | indispensable |

### Suite du classement

| # | Fonctionnalité | Problème réel résolu | Fréquence / gravité | Effort | Modèle | Classe |
|---|---|---|---|---|---|---|
| 11 | **Relecture par mot et caractère, épellation** (chemins, hash, IP, noms de branche) | tdsr, Speakup et Fenrir lisent par ligne, mot et caractère, avec épellation phonétique ([tdsr](https://github.com/tspivey/tdsr), [Speakup](http://www.linux-speakup.org/spkguide.txt)) | quotidienne, forte | S | hors modèle | important |
| 12 | **Commande corrective insérable** : la commande proposée par F10 ou `q` va sur la ligne de saisie d'une touche | Warp et ses agents proposent la correction ([Warp](https://docs.warp.dev/features/accessibility)) ; recopier une commande entendue est pénible | quotidienne, moyenne | M | **entrée changée** : nouveau mode de réponse « Commande : » sur le petit modèle | important |
| 13 | **Écho clavier et édition de ligne** : caractère tapé, mot effacé, candidats de Tab | Limite connue de steph ; Claude Code annonce le texte effacé ([doc](https://code.claude.com/docs/en/accessibility)) ; NVDA a dû corriger la relecture à droite du curseur ([NVDA](https://nvaccess.org/files/nvda/releases/2022.3/documentation/changes.html)) | chaque saisie, forte sans lecteur d'écran | M | hors modèle | important |
| 14 | **Recherche et repères dans l'historique** : aller à la commande N, chercher un mot, liste des commandes | Claude Code pose des libellés cherchables et des marques OSC 133 ([doc](https://code.claude.com/docs/en/accessibility)) ; Fenrir a des signets ([manuel](https://manpages.ubuntu.com/manpages/bionic/man1/fenrir.1.html)) | quotidienne, moyenne | S | hors modèle | important |
| 15 | **Copie** de la ligne relue ou de la sortie vers le presse-papiers | Mode copie de tdsr, presse-papiers multiples de Fenrir ([tdsr](https://github.com/tspivey/tdsr)) | quotidienne, moyenne | S | hors modèle | important |
| 16 | **Résumé de diff et de git** : « 3 fichiers, +40 −12 ; fonction parse modifiée » | Les diffs ligne à ligne sont difficiles au lecteur d'écran ([GitHub community #179647](https://github.com/orgs/community/discussions/179647)) | quotidienne (dev), moyenne | M | **entrée changée** : digest de diff (fichiers, compteurs, hunks) ; 29 exemples `git diff` | important |
| 17 | **Sorties très longues par sections** : résumé hiérarchique, puis parcours section par section | Une trace ou un `dmesg` de 2 000 lignes tronqué à `summary_chars` perd l'essentiel ; recommandation « bare mode » ([CHI 2021](https://research.google/pubs/accessibility-of-command-line-interfaces/)) | hebdomadaire, moyenne | M | **entrée changée** : le modèle reçoit des morceaux et des résumés partiels | important |
| 18 | **« Ce que j'ai manqué »** après F8 ou une absence : résumé des N dernières commandes | Une file d'annonces coupée par F8 est perdue ; les longues sessions agent sont « un silence mort » ([#70425](https://github.com/anthropics/claude-code/issues/70425)) | quotidienne, moyenne | S | **entrée changée** : entrée multi-commandes (proche du prompt QA) | important |
| 19 | **Shell distant et multiplexeurs** : marqueurs de commande dans ssh, tmux, screen | Les admins travaillent surtout sur des hôtes distants ; dans ssh steph lit les réponses mais perd codes de retour et durée | quotidienne (admins), forte | L | hors modèle, mais sorties sans statut en entrée (déjà le cas en REPL) | important |
| 20 | **Plage braille** (BRLTTY) pour les annonces | Les personnes sourdaveugles n'ont que le braille, et BRLTTY échoue sans diagnostic ([fireborn](https://fireborn.mataroa.blog/blog/i-want-to-love-linux-it-doesnt-love-me-back-post-3-speakup-brltty-and-the-forgotten-infrastructure-of-console-access/)) ; Orca le gère ([Ubuntu](https://documentation.ubuntu.com/desktop/en/latest/how-to/accessibility/orca/read-screen-in-braille/)) | rare, bloquante pour ce public | M | hors modèle | important |
| 21 | **Windows par WSL** | JAWS et NVDA couvrent 78 % des usages principaux ([WebAIM #10](https://webaim.org/projects/screenreadersurvey10/)) ; steph n'existe que sous Linux et macOS | toute la cible Windows | L | hors modèle sous WSL ; **entrée changée** si PowerShell natif | important |
| 22 | **Autres langues de sortie** : messages système en espagnol, allemand, etc., réponse dans la langue de l'utilisateur | Les sorties suivent la locale de la machine ; le corpus n'a aucune écriture non latine | selon le public, moyenne | L | **entrée changée** : sorties multilingues et langue de réponse | confort |
| 23 | **Notification quand une commande longue finit hors focus** | Claude Code sonne quand un outil de plus de 5 s finit ([doc](https://code.claude.com/docs/en/accessibility)) | hebdomadaire, faible | S | hors modèle | confort |
| 24 | **Garde-fou parlé des commandes destructrices** (`rm -rf`, `dd`, `mkfs`) : relire la commande avant Entrée | Une faute de frappe non vue est plus coûteuse sans la vue | rare, grave | S | hors modèle | confort |
| 25 | **Profils de verbosité par contexte** (ssh, REPL, build, dépôt git) | Les utilisateurs se disent submergés de bruit et réduisent la verbosité ([ASSETS 2023](https://dl.acm.org/doi/fullHtml/10.1145/3597638.3614550)) | quotidienne, faible | S | hors modèle | confort |

## Bilan pour H2

| Impact modèle | Fonctionnalités | Nombre |
|---|---|---|
| Hors modèle | 1, 5, 7, 11, 13, 14, 15, 19, 20, 21 (WSL), 23, 24, 25 | 13 |
| Entrée changée, nouvelle tâche ou nouveau prompt | 3 (F10, QA, étapes, début), 12 (commande), 18 (multi-commandes) | 3 |
| Entrée changée, nouveau digest ou nouveau type de sortie | 2 (erreurs), 4 (écran), 6 (tests), 8 (tableaux), 9 (flux), 16 (diff), 17 (sections) | 7 |
| Entrée changée, langue | 10 (anglais), 22 (autres langues) | 2 |

Point dur : le jeu d'entraînement n'a qu'un prompt système et qu'une tâche. Toute fonctionnalité de la
deuxième, troisième ou quatrième ligne sort de ce que le petit modèle a vu.

## Sources

- [Accessibility of Command Line Interfaces, CHI 2021, Google](https://research.google/pubs/accessibility-of-command-line-interfaces/) ([texte ACM](https://dl.acm.org/doi/fullHtml/10.1145/3411764.3445544))
- [Building a more accessible GitHub CLI](https://github.blog/engineering/user-experience/building-a-more-accessible-github-cli/)
- [Claude Code : mode lecteur d'écran](https://code.claude.com/docs/en/accessibility)
- [claude-code #70425 : sons, annonces humanisées, invites](https://github.com/anthropics/claude-code/issues/70425) ; [#11002](https://github.com/anthropics/claude-code/issues/11002)
- [tdsr](https://github.com/tspivey/tdsr) ; [Fenrir](https://manpages.ubuntu.com/manpages/bionic/man1/fenrir.1.html) ; [Speakup](http://www.linux-speakup.org/spkguide.txt)
- [Emacspeak : icônes sonores](https://tvraman.github.io/emacspeak/manual/Auditory-Icons.html)
- [VS Code : signaux d'accessibilité du terminal](https://code.visualstudio.com/updates/v1_89)
- [AppleVis : Terminal, VoiceOver et vim](https://www.applevis.com/forum/macos-mac-apps/how-can-you-even-use-terminal-daily-macos-voiceover-major-bugs-vim)
- [WebAIM Screen Reader Survey #10](https://webaim.org/projects/screenreadersurvey10/)
- [ToPSen : stratégies de programmeurs aveugles](https://arxiv.org/pdf/2505.22414)
- [Coding Non-Visually in VS Code, ASSETS 2023](https://dl.acm.org/doi/fullHtml/10.1145/3597638.3614550)
- [fireborn : Speakup, BRLTTY et accès console](https://fireborn.mataroa.blog/blog/i-want-to-love-linux-it-doesnt-love-me-back-post-3-speakup-brltty-and-the-forgotten-infrastructure-of-console-access/)
- [Warp : accessibilité et voix](https://docs.warp.dev/features/accessibility)

Non vérifié : les pages ACM, AppleVis et Hacker News ont refusé la lecture directe (403, 429) ; leurs
constats viennent des extraits de recherche. Aucun entretien avec un utilisateur aveugle n'a été mené.
