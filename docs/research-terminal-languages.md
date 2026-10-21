# Recherche : langues des sorties de terminal et corpus multilingue

Question posée (tâche L1 du journal de mission interne (non publié)) : steph doit-il apprendre un corpus
multilingue, et dans quelles langues ? Cette note croise trois sources : la documentation
publique des outils, une mesure locale sur ce Mac, et une mesure sur le corpus
d'entraînement existant (3 538 exemples, machines de test en locale française).

## 1. Localisation des outils de terminal

### Le mécanisme : gettext, et son absence

La plupart des outils Unix localisés utilisent `gettext` (fichiers `.po` compilés en `.mo`,
choisis selon `LANG`/`LC_MESSAGES`). Deux limites structurelles à ce mécanisme :

- il ne traduit que les messages destinés à un humain ; les outils qui doivent rester
  parsables par des scripts (Git en tête) excluent délibérément leur sortie « plomberie »
  de la traduction ;
- la traduction n'existe que si le paquet de langue est installé sur la machine. Un
  serveur minimal, un conteneur, ou macOS sans Homebrew n'a souvent aucun catalogue `.mo`
  du tout, même pour un outil qui sait théoriquement se traduire.

### État par outil (documentation + mesure croisée section 3)

| Outil | Mécanisme | Statut réel | Source |
|---|---|---|---|
| apt / dpkg | gettext, haute couverture | Largement localisé (mesuré 97,7 % FR sur apt-get dans le corpus) | [Debian l10n](https://www.debian.org/international/l10n/) |
| coreutils (GNU, `ls`, `cp`, `cat`...) | gettext via Translation Project | Localisé sur Linux si le paquet de langue est installé, traduction partielle en pratique (mesuré 51 % FR pour `ls`) | [Translation Project](https://translationproject.org/html/welcome.html) |
| make (GNU) | gettext | Partiellement localisé (mesuré 29 % FR, 65 % sortie numérique/indéterminée) | mesure locale (section 3) |
| git | gettext, mais seule la « porcelaine » est traduite par choix de design ; la « plomberie » reste anglaise pour ne pas casser les scripts | Localisation partielle et dépendante de l'installation (mesuré 26 % FR, 41 % EN) | [git po/README](https://github.com/git/git/blob/master/po/README.md) |
| gcc | gettext, traductions via Translation Project (de, es, fr, ja, ru, sv, tr, uk, vi, zh historiquement) | Diagnostics traduits mais le code source cité reste tel quel ; mesuré 14 % FR, 50 % EN | [GCC and the Translation Project](https://gcc.gnu.org/translation.html) |
| systemd / systemctl / journalctl | pas d'infrastructure gettext généralisée constatée | Quasi jamais localisé en pratique (mesuré 98 % EN pour systemctl, 79 % EN pour journalctl) | mesure locale (section 3) |
| Python (CPython) | aucune | Jamais localisé : la proposition de traduire les tracebacks a été rejetée par le projet | [bpo-16344, rejeté](https://github.com/python/cpython/issues/60548) ; mesuré 67 % EN, 3 % FR |
| npm | aucune infrastructure connue | Jamais localisé en pratique (mesuré 72 % EN, 4 % FR) | mesure locale (section 3) |
| Docker CLI | aucune, refusé explicitement | Jamais localisé ; l'équipe Docker n'a pas de plan à court terme | [docker/roadmap #564](https://github.com/docker/roadmap/discussions/564) ; mesuré 77 % EN |
| Cargo (Rust) | aucune | Jamais localisé (mesuré 80 % EN) | mesure locale (section 3) |
| ping, free, lscpu, df, du | mécanismes hétérogènes (iputils, procps, util-linux) | Sortie majoritairement numérique/tabulaire, peu de texte à traduire | mesure locale (section 3) |

**Lecture d'ensemble.** Seule une poignée d'outils système (apt/dpkg, dans une moindre
mesure coreutils et make) sont réellement et systématiquement traduits. Les outils de
développement modernes (Python, npm, Docker, Cargo, Git en grande partie, systemd)
restent anglais par choix de conception ou par absence d'effort de traduction, quelle
que soit la locale de l'utilisateur.

### Qui laisse une locale non anglaise

- **Debian** : l'installeur prend en charge 89 langues en développement (57 % de la
  population mondiale couverte pour la dernière version stable documentée). Aucune
  statistique publique fiable sur la part réelle d'installations utilisant une locale
  non anglaise n'a été trouvée (popcon ne publie pas cette donnée). Source :
  [Debian-Installer languages support](https://d-i.debian.org/doc/languages.html).
- **Monde** : environ 1,5 milliard de personnes parlent anglais (19 % de la population
  mondiale), dont seulement 372 millions en langue maternelle ; la majorité de la
  population mondiale ne parle pas anglais du tout. Source :
  [Ethnologue, via Visual Capitalist](https://www.visualcapitalist.com/ranked-the-worlds-most-spoken-languages-by-total-speakers/).
- **Europe** : 47 % des Européens déclarent parler anglais comme langue étrangère (donc
  environ la moitié ne le parle pas), et ce chiffre monte à 7 sur 10 chez les 15-24 ans.
  Source : [Eurobaromètre 540, mai 2024](https://europa.eu/eurobarometer/surveys/detail/2979).

### macOS : outils BSD non localisés, système localisé

macOS n'installe pas les outils GNU mais leurs équivalents BSD, qui n'embarquent aucune
infrastructure `gettext`. Les messages d'erreur (`ls`, `cp`, `git` fourni par les Command
Line Tools, `bash`) restent en anglais quelle que soit la locale. À l'inverse, les
composants système d'Apple (Finder, réglages, VoiceOver, formats de date) sont localisés
par le framework propre d'Apple. Preuve directe sur ce Mac en section 2.

## 2. Mesure locale sur ce Mac (lecture seule, aucune installation)

### Catalogues de traduction présents

| Élément | Résultat |
|---|---|
| Répertoires dans `/usr/share/locale` | 293 (définitions de locale : collation, dates, nombres) |
| Fichiers `.mo` (catalogues gettext réels) sous `/usr/share/locale` | **0** |
| Outillage gettext (`msgfmt`, `msgunfmt`) | présent, mais installé par Homebrew (outil de développement, pas des traductions d'applications) |

Zéro catalogue `.mo` sur l'ensemble du système confirme qu'aucun outil en ligne de
commande de ce Mac ne peut afficher un message traduit, même si `LANG` est changé.

### Commandes inoffensives sous 4 locales (`fr_FR`, `de_DE`, `es_ES`, `ja_JP`) + `C`

| Commande | Change avec `LANG` ? | Constat |
|---|---|---|
| `/bin/ls fichier_absent` (BSD réel) | Non | `ls: fichier_absent_xyz: No such file or directory` à l'identique dans les 5 locales |
| `eza` (alias `ls` de ce shell, outil Rust) | Non | Message anglais différent mais lui aussi invariant (`No such file or directory (os error 2)`) |
| `git status` hors dépôt | Non | `fatal: not a git repository...` identique dans les 5 locales (Apple Git 2.50.1, aucun `.mo` installé) |
| `python3 -c '1/0'` | Non | Traceback anglais identique dans les 5 locales |
| `bash -c 'cd /chemin/absent'` | Non | Message anglais identique |
| `df -h` (en-têtes) | Non | En-têtes anglais identiques |
| `date` | **Oui** | Seule commande qui change réellement : noms de jour/mois et ordre des champs (`dim. 27 sept. 2026` en FR, `2026年9月27日` en JA) |

**Conclusion locale sans appel.** Sur ce Mac, changer `LANG` ne change que le formatage
des dates (données de locale du système), jamais le texte des messages d'erreur ou des
diagnostics des outils testés. C'est la preuve directe de la section 1 : les outils
BSD/CLI ne sont pas localisés ici, indépendamment de toute affirmation générale.

## 3. Mesure sur le corpus d'entraînement existant

`bench/matrix/finetune/labeled/train.jsonl`, 3 538 exemples. Chaque exemple contient un
gabarit fixe en français (« Commande : ... Statut : ... Sortie : ... ») autour de la
sortie brute réelle de l'outil ; seule cette sortie brute a été classée par langue,
jamais le gabarit ni le résumé attendu (toujours en français par construction du prompt
système). Méthode : détection par accents français et vocabulaire fermé FR/EN ; sortie
vide de lettres (nombres, tableaux) classée « neutre » ; sortie sans marqueur net
classée « indéterminée ». C'est une heuristique de mots-clés, pas un détecteur de langue
validé (aucune bibliothèque de ce type n'est installée sur la machine et aucune
installation n'a été faite pour cette recherche) ; elle est fiable pour repérer le
français (accents quasi jamais présents ailleurs) et plus approximative pour trancher
entre anglais et sortie neutre.

### Répartition globale

| Langue de la sortie brute | Nombre | Part |
|---|---|---|
| Anglais | 1 409 | 39,8 % |
| Indéterminé (technique, sans marqueur de langue net) | 1 242 | 35,1 % |
| Français | 777 | 22,0 % |
| Neutre (uniquement numérique/symbolique) | 110 | 3,1 % |
| **Total** | **3 538** | 100 % |

Sur des machines pourtant réglées en locale française, moins d'un quart des sorties
brutes captées sont effectivement en français.

### Répartition par origine de machine

| Source | Total | Français | Anglais | Indéterminé | Neutre |
|---|---|---|---|---|---|
| linux-dev | 739 | 11,0 % | 47,1 % | 39,1 % | 2,8 % |
| linux-low | 680 | 41,6 % | 16,3 % | 39,9 % | 2,2 % |
| macos | 330 | 11,2 % | 45,8 % | 38,5 % | 4,5 % |
| snapshot-linux-low | 848 | 36,2 % | 29,4 % | 31,2 % | 3,2 % |
| snapshot-linux-dev | 941 | 7,3 % | 58,4 % | 30,8 % | 3,4 % |

L'écart entre `linux-dev` (11 % FR) et `linux-low` (42 % FR) montre que la part de
français dépend surtout des paquets de langue installés sur chaque machine de capture,
pas d'une propriété universelle de Linux.

### Répartition par outil (occurrences ≥ 5, sélection représentative)

| Outil | Occurrences | Français | Anglais | Indéterminé |
|---|---|---|---|---|
| apt-get | 88 | 97,7 % | 0 % | 2,3 % |
| ls | 180 | 51,1 % | 32,8 % | 16,1 % |
| find | 135 | 37,8 % | 35,6 % | 26,7 % |
| make | 110 | 29,1 % | 5,5 % | 65,5 % |
| free | 35 | 45,7 % | 2,9 % | 51,4 % |
| git | 330 | 26,4 % | 40,6 % | 33,0 % |
| gcc | 140 | 14,3 % | 50,0 % | 28,6 % |
| curl | 170 | 22,4 % | 66,5 % | 10,6 % |
| journalctl | 34 | 8,8 % | 79,4 % | 11,8 % |
| npm | 102 | 3,9 % | 71,6 % | 24,5 % |
| python3 | 209 | 2,9 % | 67,5 % | 6,7 % |
| cargo | 45 | 4,4 % | 80,0 % | 15,6 % |
| docker | 121 | 3,3 % | 76,9 % | 19,8 % |
| systemctl | 46 | 0 % | 97,8 % | 2,2 % |

Cette mesure confirme empiriquement le classement de la section 1 : apt quasi totalement
localisé, `ls`/`find` partiellement, Python/npm/Docker/Cargo/systemctl quasiment jamais.
Elle explique aussi pourquoi le banc `C1b` a dû reconstruire à la main les sorties
françaises de `git`, `free` et `lscpu` : ces outils ne les produisent pas spontanément,
même en locale `fr_FR` réelle (note déjà consignée dans le journal de mission interne (non publié), ligne
C1b).

## 4. Langues réalistes : population, lecteurs d'écran, voix Piper

Croisement du top 15 [Ethnologue](https://en.wikipedia.org/wiki/List_of_languages_by_total_number_of_speakers)
avec la disponibilité d'une interface [NVDA](https://download.nvaccess.org/releases/2024.1/documentation/userGuide.html)
traduite (54 langues hors anglais) et d'une voix
[Piper](https://github.com/rhasspy/piper/blob/master/VOICES.md) (42 langues/locales).

| Rang | Langue | Locuteurs (M) | Interface NVDA | Voix Piper | Qualité Piper max |
|---|---|---|---|---|---|
| 1 | Anglais | 1 493 | oui | oui | haute |
| 2 | Mandarin | 1 183 | oui | oui (zh_CN) | moyenne |
| 3 | Hindi | 611 | oui | oui (hi_IN) | moyenne (1 seul palier) |
| 4 | Espagnol | 561 | oui | oui (ES/MX/AR) | haute |
| 5 | Arabe standard | 335 | oui (arabe générique) | partiel (ar_JO, dialecte jordanien, pas un MSA dédié) | moyenne |
| 6 | Français | 334 | oui | oui (fr_FR) | moyenne |
| 7 | Bengali | 274 | non | **non** | - |
| 8 | Portugais | 269 | oui | oui (BR/PT) | moyenne |
| 9 | Indonésien | 255 | oui | **non** | - |
| 10 | Ourdou | 246 | oui | **non** | - |
| 11 | Russe | 210 | oui | oui (ru_RU) | moyenne |
| 12 | Allemand | 133 | oui | oui (de_DE) | haute |
| 13 | Japonais | 126 | oui | **non** | - |
| 14 | Nigerian Pidgin | 121 | non | non | - |
| 15 | Arabe égyptien | 118 | non (couvert par « arabe » générique) | non | - |

Le [rapport Piper vs Korean](https://github.com/rhasspy/piper/discussions/680) confirme
qu'il n'existe aucune voix japonaise ou coréenne viable dans l'écosystème communautaire à
ce jour. À l'inverse, VoiceOver (Apple) couvre déjà le bengali, le japonais, le coréen et
l'indonésien au niveau système ([Apple, langues VoiceOver](https://support.apple.com/en-ca/111748)) :
le verrou n'est donc pas le lecteur d'écran, mais l'absence de voix Piper de qualité
suffisante pour ces langues.

**Langues réalistes à court terme pour steph, au-delà de FR/EN** : allemand, espagnol,
portugais, russe. Les quatre ont une interface de lecteur d'écran traduite, une voix
Piper de qualité correcte à haute, et une population de locuteurs importante. Mandarin,
hindi et arabe restent des cibles à plus long terme (voix Piper existante mais un seul
palier de qualité, souvent moyen). Bengali, ourdou, japonais, indonésien sont hors de
portée tant qu'aucune voix Piper viable n'existe, indépendamment du nombre de locuteurs.

## 5. Conclusion : généralisation du modèle FR + EN, priorités de banc

### Le modèle FR + EN a-t-il des raisons de généraliser ?

Deux angles distincts, à ne pas confondre :

- **Compréhension de la sortie lue.** Un modèle entraîné sur ce corpus voit déjà 40 % de
  sorties anglaises et 35 % de sorties techniques neutres (chiffres, tableaux, chemins)
  mêlées au français cible. Un utilisateur allemand ou espagnol produira le même mélange
  dominé par l'anglais technique (sections 1 et 3). Ce chevauchement donne une raison
  concrète de penser que la lecture de la sortie généralisera correctement, sans
  entraînement dédié, à un utilisateur non francophone dont les outils restent
  eux aussi majoritairement anglais.
- **Langue de la réponse parlée.** Le prompt système actuel impose « en français » de
  façon rigide (le journal de mission interne (non publié), format des exemples). Rien dans le corpus
  n'apprend au modèle à répondre en allemand ou en espagnol si on le lui demande. C'est
  le point de rupture le plus probable, pas la compréhension de l'entrée.
- **Sorties réellement localisées** (le vrai `apt-get` allemand, le vrai `ping` russe)
  restent une distribution jamais vue dans une autre langue que le français (22 % du
  corpus actuel) : rien ne garantit que le modèle les comprenne aussi bien en allemand
  qu'en français.

### Un corpus multilingue est-il nécessaire maintenant ?

Non, pas avant d'avoir mesuré. La tâche L2 du chantier (banc sur les langues les plus
parlées, déjà planifiée après K3) est le bon endroit pour trancher, avant d'investir dans
un nouveau corpus.

### Langues à tester en priorité au banc (L2)

| Priorité | Langue | Pourquoi |
|---|---|---|
| 1 | Allemand | Meilleure couverture Piper (haute qualité) + NVDA, proximité avec le français dans le mélange anglais technique |
| 1 | Espagnol | Même niveau de couverture outillage, deuxième langue européenne la plus parlée |
| 2 | Portugais | Couverture correcte, valide un troisième cas hors du couple DE/ES |
| 2 | Russe | Script différent (cyrillique) : teste la robustesse du format de réponse sur un alphabet non latin |
| 3 (si les résultats 1-2 sont bons) | Mandarin, hindi, arabe | Population énorme mais voix Piper à qualité limitée : à réserver tant que le goulot d'étranglement voix n'est pas résolu |

Cas à tester pour chaque langue, en réutilisant la structure `C1b` (mêmes identifiants,
mêmes catégories, une fois par langue) :

1. **Changement de langue de réponse** : mêmes sorties de commande, seule l'instruction de
   langue cible change ; vérifie si le modèle répond bien dans la langue demandée.
2. **Sorties réellement localisées** : capturer de vraies sorties `apt`/`make`/`ping` en
   locale allemande, espagnole, russe (pas de reconstruction manuelle) ; vérifie si la
   compréhension tient sur du texte non anglais jamais vu à l'entraînement.
3. **Sorties anglaises/techniques inchangées** : cas déjà couverts par le corpus actuel,
   sert de témoin pour isoler ce qui régresse spécifiquement à cause de la langue.

## Sources

- [Debian l10n, statistiques centrales](https://www.debian.org/international/l10n/)
- [Debian-Installer languages support](https://d-i.debian.org/doc/languages.html)
- [Translation Project (coreutils, gcc...)](https://translationproject.org/html/welcome.html)
- [GCC and the Translation Project](https://gcc.gnu.org/translation.html)
- [git po/README (politique de traduction)](https://github.com/git/git/blob/master/po/README.md)
- [Python bpo-16344, traduction des tracebacks rejetée](https://github.com/python/cpython/issues/60548)
- [Docker roadmap #564, pas de traduction prévue](https://github.com/docker/roadmap/discussions/564)
- [Ethnologue, classement via Visual Capitalist](https://www.visualcapitalist.com/ranked-the-worlds-most-spoken-languages-by-total-speakers/)
- [Liste Wikipédia des langues par nombre de locuteurs (données Ethnologue)](https://en.wikipedia.org/wiki/List_of_languages_by_total_number_of_speakers)
- [Eurobaromètre 540, Les Européens et leurs langues, mai 2024](https://europa.eu/eurobarometer/surveys/detail/2979)
- [NVDA 2024.1, guide utilisateur (langues traduites)](https://download.nvaccess.org/releases/2024.1/documentation/userGuide.html)
- [Piper voices, VOICES.md](https://github.com/rhasspy/piper/blob/master/VOICES.md)
- [Piper, discussion sur l'absence de voix coréenne/japonaise](https://github.com/rhasspy/piper/discussions/680)
- [Apple, langues prises en charge par VoiceOver](https://support.apple.com/en-ca/111748)
- [WebAIM, 10e enquête sur les lecteurs d'écran (2024)](https://webaim.org/projects/screenreadersurvey10/)
- Mesures locales et sur corpus : ce document, sections 2 et 3 (reproductibles, aucune
  ligne du corpus citée).
