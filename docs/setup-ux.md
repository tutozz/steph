# UX de l'installation et du setup (B8a)

Analyse du 2026-09-27. Lecture seule du travail non commité de la session features
(`setup.py`, `menu.py`, `update.py`, `install.sh`, `cli.py`, `packaging/`). Aucun fichier
source modifié. Mise en œuvre : B8b.

## Méthode

| Terrain | Machine | Conditions | Nettoyage |
|---|---|---|---|
| Linux, parcours public | i5-7200U, Debian 13, 4 cœurs, sans GPU utile, fibre | utilisateur temporaire `stephux`, sans TTY (ssh sans `-t`) | `userdel -r stephux`, `/tmp` vérifié |
| Linux, étapes une à une | même i5 | artefacts publics seulement (llama.cpp, Hugging Face, PyPI) : le dépôt est privé, sa copie hors du Mac a été refusée | idem |
| Linux minimal | portable A1000, Debian 13 | inspection des prérequis, rien installé | rien créé |
| macOS | M3 Pro, ce Mac | `HOME` temporaire dans le scratchpad, copie de l'arbre de travail, port 8799, `XDG_RUNTIME_DIR` temporaire, voix coupée (`STEPH_TTS_ENABLED=0`) et journal de parole | dossiers supprimés, aucun serveur restant |

Sur Mac, le modèle de 3,2 Go n'a pas été retéléchargé : un lien symbolique vers le fichier
existant l'a remplacé (disque à 9,6 Go libres). Sa durée vient de la mesure Linux.

## Parcours actuel

1. Découverte : README (image + bloc `curl -fsSL https://steph.lsmdx.com/install | sh`) ou
   page d'accueil (`site/public/index.html`, `<pre aria-label>`).
2. `site/public/install` : exige `git`, installe `uv` si absent, clone le dépôt dans
   `~/.local/share/steph/src`, puis lance `scripts/install.sh`.
3. `scripts/install.sh` : llama.cpp (Homebrew sur Mac, sinon binaire GitHub CUDA, Vulkan ou
   CPU), modèle Gemma 4 E2B, `uv sync`, voix Piper, `uv tool install -e .`,
   puis « Installé. Lance : steph ».
4. Premier `steph` : question « Premier lancement de steph : le configurer maintenant ? »
   (dite et affichée), puis « Steph. F6 pour les paramètres. », puis démarrage du modèle.
5. Mise à jour : `steph update` (`git pull --ff-only` puis `install.sh --update`),
   `steph update --check`.
6. Désinstallation : aucune commande, aucune documentation.
7. Aucune intégration shell : `steph` se lance à la main dans chaque terminal.

## Parcours mesuré

| Étape | Durée | Frictions | Preuve |
|---|---|---|---|
| Linux, `curl ... \| sh` public | 1,7 s puis échec | `fatal : could not read Username for 'https://github.com'` ; `uv` déjà installé et `.bashrc`, `.profile`, `.zshrc` déjà modifiés | exécution `stephux`, EXIT=128 |
| Linux minimal, prérequis | - | ni `curl` ni `git` sur portable A1000 : la ligne du README ne s'exécute pas | `command -v` sur portable A1000 |
| Tag llama.cpp (API GitHub) | 1,0 s | limite de 60 appels par heure sans jeton | i5 |
| llama.cpp Vulkan, 31 Mo | 1,7 s | choisi car `libvulkan.so.1` existe, mais aucun GPU utilisé : même vitesse que CPU (17 Mo, 1,4 s) | journaux `llama-server` i5 |
| llama.cpp CUDA (NVIDIA) | non mesuré | 172 Mo + 594 Mo de `cudart`, absents du « 3 Go » annoncé | API GitHub, release b11221 |
| uv, Python 3.13, piper-tts, voix 61 Mo | 4,2 s | cache uv 172 Mo ; ligne `INFO:__main__:Downloaded: ...` | i5 |
| Modèle Gemma 4 E2B, 3,2 Go | 80 s à 40 Mo/s | environ 9 min à 50 Mbit/s, 45 min à 10 Mbit/s ; barre de progression curl en `\r` | i5 |
| Modèle Qwen3.5 0.8B, 508 Mo | 13 s | non proposé par l'installation | i5 |
| Mac, `install.sh` avec llama.cpp Homebrew | 9 s | conseil `brew install sox` affiché | `HOME` temporaire |
| Mac, `install.sh` sans Homebrew | 11 s | llama.cpp 11,8 Mo en 1 s | `HOME` temporaire, `PATH` sans `/opt/homebrew/bin` |
| Mac, `install.sh --check` | < 1 s | dit quoi, pas combien de Go ni combien de temps | `HOME` temporaire |
| Premier `steph` : première phrase | 0,6 à 0,9 s | « Steph. F6 pour les paramètres. » | `STEPH_SPEECH_LOG` |
| Modèle prêt, Mac Metal | 11,9 s | rien n'est dit quand il est prêt | `llama-server.log` |
| Modèle prêt puis première réponse, i5 CPU, Gemma | 3,0 s puis 4,4 s | 12,4 jetons/s | i5 |
| Idem, Qwen3.5 0.8B | 1,7 s puis 1,9 s | - | i5 |
| Piper, première phrase à froid, i5 | 1,9 s | - | i5, `t.wav` |

Temps jusqu'à la première phrase utile, fibre : environ 2 minutes. Avec 50 Mbit/s :
10 à 12 minutes, dont 9 de silence pendant le modèle.

## Accessibilité : ce qu'entend une personne aveugle

Avant que steph parle, seul le lecteur d'écran (Orca, VoiceOver) porte l'installation.

| Moment | Ce qui s'affiche | Au lecteur d'écran |
|---|---|---|
| Installation de uv | 8 lignes en anglais, dont `source $HOME/.local/bin/env` | lisible, mais bruit hors sujet |
| Échec du clone | message git en anglais, sans cause ni suite | on ne sait pas que le dépôt est privé |
| Téléchargement du modèle | barre curl réécrite en `\r` chaque seconde | illisible ou muette ; aucune estimation |
| Voix | `INFO:__main__:Downloaded: fr_FR-siwis-medium` | jargon de journal |
| Fin | « Installé. Lance : steph » | aucun son joué ; `steph` peut être hors `PATH` |
| Premier `steph` | question dite et affichée, oui ou non | bon ; première voix entendue |
| Setup | questions numérotées, réponse au clavier, Entrée pour garder | bon ; pas de TUI, pas de couleur |
| Erreur de démarrage | « le modèle local n'a pas démarré. Résumés simplifiés. » | dit, mais sans cause ni remède |
| Exception Python | trace colorée en anglais | illisible (cas mesuré : chemin de socket trop long) |

Constat : la voix Piper tient en 230 Mo et parle en 1,9 s à froid sur l'i5. Téléchargée
avant le modèle, elle peut confirmer le son et annoncer la suite pendant les 3,2 Go.

## Défauts classés par gravité

### Critiques

| # | Défaut | Preuve | Fichier |
|---|---|---|---|
| C1 | La ligne publique échoue pour tout inconnu : dépôt privé, message git brut, après avoir installé uv et modifié trois fichiers de démarrage du shell | i5, EXIT=128 en 1,7 s | `site/public/install` |
| C2 | `steph setup` sans TTY enregistre les valeurs par défaut en silence : fin de fichier lue comme Entrée. Le fichier créé fige un chemin absolu de voix et supprime la proposition du premier lancement. Avec B7 sous `curl \| sh`, stdin est le tuyau : le cas deviendra la règle | `steph setup < /dev/null`, EXIT=0, `config.toml` écrit | `src/steph/setup.py` (`_Voice.ask`, `run_setup`) |
| C3 | Aucun son n'est joué pendant ni à la fin de l'installation. Voix absente : repli silencieux sur la voix système. Linux sans lecteur audio ni `spd-say` : silence total, sans message | lecture de `tts.py:74-85`, `audio.py:20-60` | `scripts/install.sh`, `src/steph/audio.py` |
| C4 | `steph` peut être hors `PATH` juste après « Lance : steph » : `uv tool install -q` tait l'avertissement. Cas type : Mac avec `brew install uv`, où `~/.local/bin` n'est pas dans le `PATH` | journal d'installation Mac sans avertissement | `scripts/install.sh` |
| C5 | Prérequis non gérés : Debian minimal sans `curl` ni `git` ; Linux arm64 reçoit le binaire x64 (`FLAVOR=ubuntu-x64` en dur) ; macOS neuf sans outils de ligne de commande ouvre une fenêtre graphique au premier `git` ou `python3` | portable A1000 ; lecture de `install.sh` ; macOS neuf non exercé | `site/public/install`, `scripts/install.sh` |

### Majeurs

| # | Défaut | Preuve | Fichier |
|---|---|---|---|
| M1 | 3,2 Go sans progression lisible ni durée estimée : barre curl en `\r` | journal `install.sh` Mac, bloc `% Total` | `scripts/install.sh` |
| M2 | Taille annoncée fausse : « 3 Go » ; réel 3,6 Go sans GPU, 4,4 Go avec NVIDIA (CUDA 766 Mo, uv et Python 400 Mo) | mesures i5, API GitHub | `README.md`, `README.fr.md`, `site/public/index.html` |
| M3 | Aucun choix de modèle : Gemma 3,2 Go partout, alors que `options.json` recommande Qwen 0.8B (508 Mo) sur N1 et N2. Mesuré sur l'i5 : 1,9 s contre 4,4 s | i5 ; `docs/voice-bench/rtx3060/options.json` | `scripts/install.sh`, `src/steph/setup.py` (B4, B6) |
| M4 | Erreurs de démarrage sans cause ni remède : modèle absent et binaire absent donnent la même phrase ; toute exception sort en trace anglaise colorée | `STEPH_MODEL=/nonexistent`, `STEPH_LLAMA_SERVER=/nonexistent` ; trace `AF_UNIX path too long` | `src/steph/cli.py`, `src/steph/llm.py` |
| M5 | Pas de désinstallation. Fichiers répartis dans six endroits : `~/.local/share/steph` (modèles, voix, `src`), `~/.config/steph`, `~/.local/share/uv/tools/steph`, `~/.local/bin/steph`, `/tmp/steph-<uid>`, fichiers de démarrage modifiés par l'installeur uv | inventaire du `HOME` temporaire | nouveau : `steph uninstall` |
| M6 | Ordre défavorable : la voix vient après le modèle, donc steph ne peut rien dire pendant l'attente | `install.sh`, sections dans l'ordre | `scripts/install.sh` |

### Mineurs

| # | Défaut | Fichier |
|---|---|---|
| m1 | Bruit : `INFO:__main__:Downloaded`, « Conseil : brew install sox » | `scripts/install.sh` |
| m2 | Chemins fixes `/tmp/llama.tgz` et `/tmp/cudart` : collision entre utilisateurs | `scripts/install.sh` |
| m3 | Vulkan choisi dès que la bibliothèque existe, même sans GPU utilisable (14 Mo de plus, aucun gain sur l'i5) | `scripts/install.sh` |
| m4 | Setup : « F7 à F10 » oublie F6 ; voix listée « siwis medium » sans description ; « non » renvoie le code 1 ; « Réponse non comprise » ne rappelle pas les choix valides | `src/steph/setup.py` |
| m5 | `--check` ne donne ni taille ni durée | `scripts/install.sh` |
| m6 | CUDA 12.8 exige un pilote récent ; pilote ancien : échec générique au lancement (lecture de code) | `scripts/install.sh` |
| m7 | Rien n'annonce que le modèle est prêt (11,9 s sur Mac) | `src/steph/cli.py` |
| m8 | README : « Prérequis : uv » alors que la ligne publique l'installe ; section Mac qui demande `brew install uv llama.cpp sox` au lieu de la ligne unique | `README.md`, `README.fr.md` |

## Comparaison aux installeurs de référence

| Pratique | rustup | Ollama | Homebrew | uv | steph |
|---|---|---|---|---|---|
| Plan annoncé avant d'agir | oui | lignes `>>>` | liste « will install » | non | non |
| Confirmation, lue sur `/dev/tty` | oui | non | Entrée pour continuer | non | non |
| Mode non interactif explicite | `-y` | implicite | `NONINTERACTIVE=1` | implicite | implicite, mais le setup écrit quand même |
| Progression | barres | barre curl | lignes `==>` | silencieux | barre curl |
| `PATH` : ce qui est modifié est dit | oui | sans objet | « Next steps » | oui | non |
| Désinstallation | `rustup self uninstall` | documentée | script dédié | documentée | aucune |

Bonnes pratiques d'accessibilité retenues :
- Sampath et al., CHI 2021 : les utilisateurs de lecteur d'écran préfèrent une sortie nue,
  sans animation ni décoration, avec des étapes en texte et des erreurs actionnables.
- GitHub CLI (v2.72) : `spinner disabled` remplace l'animation par des lignes de texte ;
  le prompteur accessible pose des questions linéaires lisibles par la synthèse.
- clig.dev : détecter le TTY, `--no-input`, `NO_COLOR`, une ligne par événement.

Avantage propre à steph : il possède une voix. Aucun de ces installeurs ne peut dire
« le son fonctionne » ; steph le peut dès la 5e seconde.

## Recommandations classées par rendement

Rendement = effet sur l'utilisateur divisé par le coût. Porteur : **features** pour les
fichiers qu'elle a en cours (`setup.py`, `menu.py`, `update.py`, `install.sh`, `cli.py`,
`packaging/`) ; **B8b** pour le reste, ou pour ces fichiers après le commit de features.

| Rang | Recommandation | Défauts | Effet | Coût | Fichier | Porteur | Critère de preuve |
|---|---|---|---|---|---|---|---|
| 1 | Setup : lire les réponses sur `/dev/tty` ; sans TTY, ne rien écrire et sortir avec un message ; fin de fichier n'est jamais une réponse | C2 | fort | faible | `src/steph/setup.py`, appel B7 dans `scripts/install.sh` | features | test : `steph setup < /dev/null` ne crée pas `config.toml` ; `curl \| sh` sous pseudo-TTY pose les questions |
| 2 | Voix d'abord : `uv sync` et voix avant llama.cpp et modèle, puis `steph say` : « Installation de steph. Si vous m'entendez, le son fonctionne. » Question « Entendez-vous la voix ? » ; sinon message sur le lecteur audio manquant | C3, M6 | fort | faible | `scripts/install.sh` | features (B7), sinon B8b après commit | journal `STEPH_SPEECH_LOG` : la phrase précède le début du téléchargement du modèle |
| 3 | Progression en lignes : `curl --no-progress-meter`, une ligne toutes les 10 % ou 30 s (« Modèle : 40 %, environ 3 minutes ») ; dite par steph tous les 25 % | M1 | fort | faible | `scripts/install.sh` | B8b après commit | journal d'installation sans `\r` ; test sur un faux serveur lent |
| 4 | Fin fiable : vérifier `command -v steph` ; sinon donner le chemin absolu et la ligne exacte à ajouter au shell ; dire « steph est prêt » | C4 | fort | très faible | `scripts/install.sh` | B8b après commit | `HOME` neuf, `PATH` sans `~/.local/bin` : le message apparaît |
| 5 | Ligne publique robuste : vérifier `curl`, `git`, architecture ; message en français avec la commande du gestionnaire de paquets ; échec du clone expliqué ; alternative `wget` | C1, C5 | fort | faible | `site/public/install` | B8b | exécution sur Debian minimal (portable A1000) et sur l'i5 : message clair, rien modifié avant l'échec |
| 6 | Plan annoncé : 4 lignes au départ (ce qui sera installé, taille pour cette machine, durée estimée, emplacement), confirmation sur `/dev/tty`, `STEPH_YES=1` pour sauter | M2, m5 | moyen | faible | `scripts/install.sh` | B8b après commit | test sans TTY : pas de blocage ; sous pseudo-TTY : question posée |
| 7 | Choix du modèle selon le matériel dans le setup, depuis le catalogue : recommandé par défaut, taille et vitesse dites | M3 | fort | moyen | `src/steph/setup.py`, `src/steph/data/catalog.json` | features (B4, B6) | test : sur profil N1 simulé, le défaut est le petit modèle |
| 8 | Erreurs actionnables : « Modèle introuvable. Lancez steph update. » ; « llama.cpp introuvable » ; exceptions attrapées au niveau de `main`, message français court et chemin du journal | M4 | moyen | faible | `src/steph/cli.py`, `src/steph/llm.py` | B8b après commit | tests : `STEPH_MODEL` et `STEPH_LLAMA_SERVER` invalides donnent deux phrases distinctes ; aucune trace à l'écran |
| 9 | Dire « Modèle prêt. » à la fin du chargement | m7 | moyen | très faible | `src/steph/cli.py` | B8b après commit | journal de parole |
| 10 | `steph uninstall` : liste ce qui sera supprimé, confirmation, option pour garder les modèles | M5 | moyen | moyen | `src/steph/cli.py`, nouveau module | features | `HOME` temporaire vide après exécution, sauf modèles si demandé |
| 11 | Architecture Linux : arm64 prend `ubuntu-arm64` ou `ubuntu-vulkan-arm64` ; Vulkan seulement si un périphérique répond | C5, m3 | moyen | faible | `scripts/install.sh` | B8b après commit | test de sélection sur `uname -m` simulé |
| 12 | Hygiène : `mktemp` au lieu de `/tmp/llama.tgz` ; taire le journal Piper ; conseil sox une seule fois | m1, m2 | faible | très faible | `scripts/install.sh` | B8b après commit | journal d'installation |
| 13 | README et site : tailles par profil, `PATH`, désinstallation, mention « installation lisible au lecteur d'écran », ligne unique aussi sur Mac | M2, m8 | moyen | faible | `README.md`, `README.fr.md`, `site/public/index.html` | B8b | relecture ; chiffres identiques aux mesures ci-dessus |
| 14 | Setup : F6 dans l'annonce des touches, description des voix, code 0 sur « non », choix valides rappelés | m4 | faible | très faible | `src/steph/setup.py` | features | tests existants étendus |

Ordre conseillé pour B8b : 1 à 5 d'abord, car ce sont eux qui décident si une personne
aveugle arrive seule jusqu'à la première phrase.

## Non exercé

| Élément | Raison |
|---|---|
| Parcours complet de steph sur Linux | copie du dépôt privé vers l'i5 refusée ; étapes mesurées avec les artefacts publics seulement |
| Son réel, Orca, VoiceOver | voix coupée pendant les essais Mac ; aucun lecteur d'écran lancé ; recette humaine nécessaire |
| macOS neuf sans outils de ligne de commande ni Homebrew | exigerait de modifier le système réel |
| `brew install llama.cpp` par l'installeur | llama.cpp déjà présent par Homebrew sur ce Mac |
| Chemin NVIDIA CUDA de bout en bout | portable A1000 sans `curl` ni `git`, installation système interdite |
| Disque plein, coupure réseau pendant le modèle | déduits du code : `set -e` sort sur l'erreur curl brute ; le `.part` reprend avec `-C -` |
| Mise à jour réelle (`steph update` sans `--check`) | le clone de test n'avait pas de dépôt distant |

## Après B8b

Mise en œuvre du 2026-09-27, en TDD (72 tests ajoutés, suite complète verte : 861 et 3 810).
Commits `5ee66f7` à `1d4ec69`. Rien n'est publié ni déployé : `site/public/install` n'est
servi qu'après un déploiement du site.

### Remédiations

| # | Reco | État | Preuve |
|---|---|---|---|
| 1 | Setup lu sur `/dev/tty`, sans TTY rien n'est écrit | fait | `steph setup < /dev/null` sans terminal : EXIT=1, aucun `config.toml` ; sous pseudo-TTY avec stdin en tuyau (`yes 9 \|`), questions posées et réponses du terminal enregistrées |
| 2 | Voix d'abord, steph parle, message si aucun son | fait | journal de parole : première phrase à 9,9 s, avant llama.cpp (11,0 s) et le modèle (12,4 s) ; `steph say` sort en 1 avec la cause si aucun lecteur audio |
| 3 | Progression en lignes, dite tous les 25 % | fait | `steph.fetch` : une ligne par dizaine, durée restante, zéro `\r` dans le journal ; 25, 50, 75 % et « téléchargé » dits |
| 4 | Fin : `command -v steph`, sinon chemin et ligne du shell | fait | vérifié sur le PATH de la personne, pas celui de l'installeur ; chemin absolu et `export PATH=...` pour `~/.zshrc` |
| 5 | Script public : curl, git, tar, architecture, locale, rien modifié avant | fait | i5 : dépôt privé, 0,3 s, message FR puis EN, `.bashrc` et `.profile` identiques (md5) ; sans git : `sudo apt-get install git` proposé |
| 6 | Plan annoncé | partiel | ligne de taille pour cette machine ; pas de confirmation `/dev/tty` ni `STEPH_YES` |
| 7 | Modèle selon le matériel | point d'accroche | `catalog.py` lit `data/catalog.json` (schéma de `options.json`), niveau N1 à N4 ou GPU, question du modèle dans le setup si le fichier existe ; aucune entrée inventée, l'installeur télécharge encore Gemma partout |
| 8 | Erreurs modèle et llama.cpp distinctes | fait | « Modèle introuvable : ... Lancez steph update » contre « llama.cpp introuvable » ; le chemin du journal dans l'échec générique |
| 10 | `steph uninstall` | fait | liste, confirmation sur le terminal, `--keep-models`, `--yes` ; restes signalés au lieu d'un succès affiché |
| 11 | arm64 Linux | fait | `ubuntu-arm64`, `ubuntu-vulkan-arm64`, `ubuntu-cuda-13.4-arm64` ; architecture inconnue refusée avec un message |
| 12 | Hygiène | fait | `mktemp -d` au lieu de `/tmp/llama.tgz` ; journal Piper tu ; conseil sox en installation seulement |
| 13 | Tailles exactes | fait | 3,6 Go et 4,4 Go dans les deux README, le site, l'image d'installation ; Homebrew : 3,2 Go et 61 Mo |
| 14 | Setup : F6, relecture, code 0 sur « non », choix rappelés | fait | neuf touches configurables ; débit 0,5 à 3 dans le setup et le menu (bornes partagées) |
| - | Setup et menu en anglais | fait | `language = "en"` : setup, menu F6, aide des touches via `strings.py` |
| - | `STEPH_PROMPT_TAG` | retiré | le shell ne lit que `STEPH_MENU_KEY` |
| - | IP LAN dans `test_pronounce.py` | remplacée | `192.0.2.16` (RFC 5737) |

Non faits : confirmation du plan (reco 6), « Modèle prêt. » (reco 9), exceptions
attrapées dans `main` (trace anglaise possible), Vulkan seulement si un périphérique
répond (m3), contrôle du pilote CUDA (m6), setup lancé par l'installation (B7), section
Mac du README qui demande encore `brew install uv llama.cpp sox` (m8).

### Mesures avant et après

| Mesure | Avant (B8a) | Après (B8b) | Terrain |
|---|---|---|---|
| Ligne publique, dépôt privé | 1,7 s, `fatal: could not read Username`, uv installé, trois fichiers du shell modifiés | 0,3 s, « dépôt inaccessible ... Rien n'a été modifié. », dossier personnel inchangé | i5, utilisateur temporaire |
| Outil manquant | la ligne ne s'exécute pas, sans explication | « git est requis. Installez-le : sudo apt-get install git » | i5, PATH restreint |
| `steph setup < /dev/null` | EXIT=0, `config.toml` écrit | EXIT=1, message, aucun fichier | Mac, `HOME` temporaire |
| Première phrase de steph | au premier `steph`, après l'installation (environ 2 min sur fibre) | 9,9 s après le début de l'installation | Mac, uv neuf, sans Homebrew |
| Progression du modèle | barre curl en `\r` | 9 lignes (10 à 90 %) avec durée restante, 4 annonces vocales | Mac, Qwen3.5 2B, 1,3 Go en 27 s |
| Installation complète | 11 s sans le modèle | 39,5 s dont 27 s de modèle | Mac, uv neuf, llama.cpp GitHub, Qwen3.5 2B |
| Fin, `steph` hors PATH | « Installé. Lance : steph » | chemin absolu et ligne `export PATH=...` pour `~/.zshrc` | Mac, PATH `/usr/bin:/bin` |
| Désinstallation | aucune | 1,6 s, 1,6 Go supprimés | Mac, pseudo-TTY, réponse « o » |

Reste après `steph uninstall` : uv (`~/.local/bin/uv`, son cache de 157 Mo, Python 68 Mo)
et la base de télémétrie d'onnxruntime (`~/Library/Application Support/Microsoft/DeveloperTools/.onnxruntime`),
créée par Piper. Aucun fichier de démarrage du shell n'est créé ni modifié.

### Pièges trouvés pendant la recette réelle

| Piège | Effet sans correction | Correction |
|---|---|---|
| `open("/dev/tty", "r+")` échoue sur tout vrai terminal (flux non positionnable) ; les tests unitaires simulaient le terminal | `steph setup` refusait partout, même dans un terminal | deux flux, test sous pseudo-TTY (`c70eb41`) |
| Le script public ajoute `~/.local/bin` à son propre PATH | « Lancez : steph » affiché alors que le terminal de la personne ne le trouve pas | `STEPH_USER_PATH` transmis à `install.sh` |
| llama.cpp reçu en 1,4 s | neuf lignes identiques d'un coup | une ligne par relevé, rien si fini entre deux relevés |
| Voix coupée | avancement vocal absent du journal, donc invérifiable | `Speaker` créé même voix coupée |
| `RUNTIME_DIR.parent` sous Linux vaut `XDG_RUNTIME_DIR` | `steph uninstall` aurait supprimé `/run/user/<uid>` entier | seul `/tmp/steph-<uid>` part en entier, test dédié |
| `.DS_Store` recréé par macOS pendant la suppression | reste silencieux, « désinstallé » affiché | deux passes, restes listés, code 1 |
| steph lancé par son chemin absolu | `uv` hors PATH, `uv tool uninstall` sauté | uv cherché aussi dans `~/.local/bin` |

### Non exercé après B8b

| Élément | Raison |
|---|---|
| Installation Linux complète | copie de l'arbre privé vers l'i5 non tentée (refusée en B8a) ; seul le script public y a tourné |
| Son réel, Orca, VoiceOver | voix coupée (`STEPH_TTS_ENABLED=0`), journal de parole seulement ; recette humaine |
| `steph say` sans lecteur audio sur un vrai Linux | test unitaire seulement |
| Linux arm64, CUDA | sélection du binaire testée sur `uname` simulé |
| macOS sans outils de ligne de commande | branche `xcode-select -p` jamais exécutée |
| Gemma 4 E2B (3,2 Go) par le nouvel installeur | Qwen3.5 2B (1,3 Go) utilisé, 8 Go libres sur le Mac |
| Messages « Modèle introuvable » dans une vraie session `steph` | tests unitaires seulement |
| `steph uninstall` sous Linux | tests unitaires seulement |
| `steph update` réel | clone de test sans mise à jour distante utile |

Piège connu, non corrigé : `STEPH_MODEL=qwen` choisit le modèle de l'installeur mais
surcharge aussi `model` dans `load_config` ; exporté dans le shell, steph dirait
« Modèle introuvable : qwen ».

## Sources

- [Accessibility of Command Line Interfaces, CHI 2021](https://dl.acm.org/doi/10.1145/3411764.3445544)
- [Building a more accessible GitHub CLI](https://github.blog/engineering/user-experience/building-a-more-accessible-github-cli/)
- [Using Git, GitHub CLI, and Copilot CLI with a Screen Reader](https://accessibility.github.com/documentation/guide/cli/)
- [Command Line Interface Guidelines](https://clig.dev/)
