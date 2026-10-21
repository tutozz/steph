# G3c, données : sorties publiques en bac à sable

Piste 4, étape données. **Rien n'est étiqueté** ; rien n'est entraîné.

**Résultat : 1 779 sorties retenues** (FR 883, EN 896), PII 0, contamination 0 contre le banc v3 entier.
C'est 2,3 fois R2-C4 (784) et 1,5 fois R2-C2 et R2-C4 réunis (1 222).

## Critères

| Critère | Cible | Mesuré | Tenu |
|---|---|---|---|
| Sorties retenues | 1 200 à 2 000, FR et EN | **1 779** (FR 883, EN 896) | oui |
| Familles faibles d'abord | taxonomie de `docs/deterministic-aids.md` | fichiers 314, tests 302, lint 274, build 139, paquets 144 | oui |
| Familles absentes du corpus | tests, lint et typage, make/configure, docker, bases, réseau, services, paquets, scripts | toutes présentes, voir le tableau | oui |
| PII (`audit_pii.py`) | 0 | **0** sur `public_g3c.retained.jsonl` ; 25 exécutions écartées au filtre | oui |
| Contamination (`leak_check.py drop`, banc v3 entier) | 0 | **0 retirée** au drop ; `scan` : 0 cas rejeté, Jaccard lignes max 0,333, shingles max 0,5, canari 0 | oui |
| Licence et commit par source | chaque source | 37 dépôts, commit épinglé, licence lue dans le dépôt : `data/sources.json` | oui |

`docs/code-first-d6.md` n'existait pas au lancement : la priorité vient de la taxonomie de `docs/deterministic-aids.md` (build-native, fichiers, scripts, tests, paquets, lint).

## Comptes par famille et par langue

| Famille (v3) | FR | EN | Total | Dont code de sortie non nul |
|---|---:|---:|---:|---:|
| files | 153 | 161 | 314 | 82 |
| tests | 151 | 151 | 302 | 102 |
| lint-format | 137 | 137 | 274 | 132 |
| bases (data) | 78 | 77 | 155 | 69 |
| packages-system | 70 | 74 | 144 | 61 |
| build-native (make, configure, cmake, cargo, npm build) | 68 | 71 | 139 | 38 |
| docker (containers) | 43 | 43 | 86 | 28 |
| vcs-git | 39 | 38 | 77 | 24 |
| typage (mypy, tsc) | 32 | 32 | 64 | 38 |
| services-logs | 30 | 30 | 60 | 44 |
| network-transfer | 23 | 23 | 46 | 30 |
| shell-scripts | 18 | 18 | 36 | 16 |
| python | 16 | 16 | 32 | 14 |
| network | 15 | 15 | 30 | 14 |
| rust-go | 6 | 6 | 12 | 0 |
| js-node | 3 | 3 | 6 | 4 |
| processes | 1 | 1 | 2 | 0 |
| **Total** | **883** | **896** | **1 779** | **696** |

- 579 commandes distinctes ; 793 exécutions avec panne injectée ; 32 sorties vides.
- `rust-go`, `js-node` et `processes` sont petits : le filtre de contamination les a vidés (commandes identiques au Steph Speak Bench, lignes communes avec v3). Leurs sorties de tests, lint et build sont comptées dans ces familles.

## Chaîne

| Étape | Machine | Détail |
|---|---|---|
| Racine | RTX 3060, CPU | Debian 13 `images.linuxcontainers.org` trixie 20260930 (sha256 `d1a43aed…`), outils installés **dans la racine** par `chroot_net.sh`, `setup_rootfs.sh`, `setup2.sh` ; rien d'installé sur l'hôte |
| Sources | RTX 3060 | `fetch_g3c.py` : archive `codeload` de la branche par défaut, commit lu dans l'en-tête pax, licence lue dans le dépôt ; rejet hors MIT, Apache-2.0, BSD, ISC, Zlib, PostgreSQL, CC0, Unlicense (lz4 écarté : GPLv2 hors `lib/`) ; dépendances npm, cargo et Go prises à cette étape, **seul moment avec réseau** |
| Gabarit | bac à sable | `build_base.sh` : fichiers, scripts, bases, dépôts git, certificats et configurations **inventés**, noms fictifs, domaines `.invalid` ; grappe PostgreSQL 17 avec Chinook et Pagila |
| Exécution | RTX 3060, cœurs 6-11, `Nice=19`, `MemoryMax=10G` | `gen_g3c.py` : **1 450 scénarios, 2 900 exécutions**, `fr_FR.UTF-8` puis `C.UTF-8` ; `sbx.sh` : `unshare` réseau, pid, uts, ipc et montage, racine en lecture seule, uid 1000, `HOME` sur un tmpfs jetable, hôte `machine-demo` ; pannes par `mut.py` dans la préparation cachée |
| Filtre | Mac (script léger, 4 s) | `filter_g3c.py` : règles de R2-C4 p3, plus doublons exacts de T7 et R2-C4 p1-p3 ; `leak_check.py drop` contre les 1 105 cas des lots v3 ; `audit_pii.py` |

Décompte du filtre :

| Étape | Exécutions |
|---|---:|
| Brutes | 2 900 |
| Sortie identique au-delà de 2 par langue | -375 |
| Sortie vide au-delà de 40 | -98 |
| Doublon exact d'un corpus public antérieur (T7, R2-C4) | -60 |
| Trace de l'hôte (`uname`, noyau `-pve`, mémoire hôte, chemin du gabarit) | -6 |
| Délai dépassé | -2 |
| Contamination (une exécution peut toucher plusieurs règles) | -555 |
| PII | -25 |
| **Retenues** | **1 779** |

Règles de contamination touchées : 3 lignes longues communes avec un cas v3 255, même commande v3 et Jaccard ≥ 0,15 197, commande du Steph Speak Bench 124, empreintes `fingerprints.txt` 157, Jaccard lignes ≥ 0,5 98, ligne longue du Speak Bench 87, shingles ≥ 0,6 52, banc de 36 cas 52.

## Pannes injectées

| Famille | Pannes |
|---|---|
| tests | retour neutralisé, comparaison inversée, décalage d'une unité, erreur de syntaxe, module supprimé, paquet non installé, fichier de test absent, `-W error`, `--maxfail`, `-x` ; pytest, mocha, vitest, `node --test`, `go test`, `cargo test`, bats |
| lint et typage | variable inutilisée, syntaxe, indentation ; ruff, flake8, pylint, black, mypy, eslint, prettier, tsc, `go vet`, gofmt, clippy, rustfmt, shellcheck |
| make, configure, cmake | configure non lancé ou non généré, options inconnues, compilateur absent, `-Werror`, en-tête supprimé, point-virgule retiré, `make install` vers un préfixe en lecture seule, cible mal écrite, générateur Ninja absent, `make check` et `ctest` |
| bases | PostgreSQL 17 (Chinook, Pagila, base inventée) : table, colonne, syntaxe, clés, CHECK, NOT NULL, rôle et base inexistants, serveur arrêté, mauvais port, verrou, droits du répertoire de données ; Valkey : mauvais type, arguments, port occupé ; SQLite |
| docker | client seul : démon absent, socket refusée, compose `config` sur awesome-compose et sur des fichiers cassés (indentation, clé inconnue, `env_file` absent, variable non définie) |
| réseau | serveurs locaux (http, API 200/404/500, TLS autosigné et expiré, serveur muet) ; refus, nom introuvable, réseau injoignable, pas de DNS, `ping` sans capacité |
| services | `nginx -t` sur 8 configurations, port occupé, rechargement sans maître, 502 ; `sshd -t` ; systemctl et journalctl sans systemd ; crontab |
| paquets | `apt-get -s`, apt sans droits, dpkg, pip géré par le système, pip et npm hors ligne, `go mod tidy`, `cargo add` hors ligne |
| git | dépôts inventés : conflits de fusion, rebase, cherry-pick, remisage, push refusé, pull divergent, remote introuvable, tête détachée, bisect |

## Sources et licences

Commits du 2026-10-01, branche par défaut. « AND » dans `sources.json` note plusieurs fichiers de licence dans le dépôt ; pour walkdir, glob, either et fnv, c'est un double choix (MIT **ou** Apache-2.0, ou Unlicense).

| Source | Commit | Licence | Usage |
|---|---|---|---|
| python-attrs/attrs | `8f767776326f` | MIT | tests, lint, typage, fichiers |
| pytoolz/toolz | `451af60dec59` | BSD-3-Clause | tests, lint |
| astanin/python-tabulate | `268615a5c27d` | MIT | tests, lint |
| kjd/idna | `c79316ffefd0` | BSD-3-Clause | tests, lint |
| tkem/cachetools | `3c082c654c28` | MIT | tests, lint |
| pyparsing/pyparsing | `f803ae834288` | MIT | tests, lint |
| grantjenks/python-sortedcontainers | `3ac358631f58` | Apache-2.0 | tests, lint |
| jquast/wcwidth | `5f185b351234` | MIT | tests, lint |
| pytest-dev/iniconfig | `00e7d87c7353` | MIT | tests, lint |
| marshmallow-code/marshmallow | `7f0792bd7a06` | MIT | tests, lint |
| visionmedia/bytes.js | `9ddc13b6c66e` | MIT | tests, lint, paquets |
| jshttp/content-type | `d005d8bfd984` | MIT | tests, typage, build |
| jshttp/statuses | `770a97d931c1` | MIT | tests, lint |
| jshttp/http-errors | `814207e1f69e` | MIT | tests, lint |
| jshttp/negotiator | `14b0a7b88e7e` | MIT | tests, lint |
| jshttp/vary | `1220b9c487f9` | MIT | tests, lint, fichiers |
| gorilla/mux | `db9d1d0073d2` | BSD-3-Clause | tests, build, vet, fichiers |
| julienschmidt/httprouter | `484018016424` | BSD-3-Clause | tests, build |
| BurntSushi/toml | `d733fc535e4a` | MIT | tests, build |
| pkg/errors | `87f8819acf6d` | BSD-2-Clause | tests, build |
| google/btree | `aeba20f7a1e1` | Apache-2.0 | tests, build |
| BurntSushi/walkdir | `6fd031c82ba5` | MIT ou Unlicense | cargo, fichiers |
| rust-lang/glob | `cfa2a58f2e44` | MIT ou Apache-2.0 | cargo |
| rayon-rs/either | `ce6f07fc3d56` | MIT ou Apache-2.0 | cargo |
| servo/rust-fnv | `4e55052a343a` | MIT ou Apache-2.0 | cargo |
| yaml/libyaml | `90a56d4500aa` | MIT | configure, make, cmake |
| akheron/jansson | `851a2145e325` | MIT | configure, make, cmake |
| libexpat/libexpat | `084c14ca2827` | MIT | configure, make, cmake, fichiers |
| madler/zlib | `767c4c947852` | Zlib | configure, make |
| libuv/libuv | `7a02ab5f400e` | MIT | configure, make, cmake, fichiers |
| alexanderepstein/Bash-Snippets | `581a6b4ea681` | MIT | shellcheck, bats |
| nvie/gitflow | `d2eee63886e2` | BSD-2-Clause | shellcheck, make |
| dylanaraps/pure-bash-bible | `8c19d0b482b0` | MIT | récupéré, non utilisé |
| junegunn/fzf | `b1be3a8be1b8` | MIT | scripts d'installation, shellcheck |
| lerocha/chinook-database | `7f67772503d7` | MIT | PostgreSQL |
| devrimgunduz/pagila | `9baf49c4149e` | MIT (fichier du dépôt) | PostgreSQL |
| docker/awesome-compose | `30f4b7f6a6c3` | CC0-1.0 | docker compose, fichiers |

| Outil (sorties seules) | Licence |
|---|---|
| Debian 13 : gcc 14, make, cmake, autotools, coreutils, git, apt, dpkg, bash, curl, wget, openssl, nginx 1.26, OpenSSH, PostgreSQL 17, Valkey 8, SQLite, Go, Rust 1.85, Node 20, Python 3.13 | licences des paquets Debian, non redistribués |
| ruff, black, flake8, pylint, mypy, eslint 9, typescript 5, prettier 3, docker CLI et compose | MIT, Apache-2.0, GPL (pylint) ; sorties seules |

Fichiers inventés (gabarit, 628 sorties) : CC BY 4.0. Le jeu dérivé peut partir sous CC BY 4.0 avec l'attribution de chaque dépôt.

## Doutes

- **Rien n'est étiqueté.** La qualité des étiquettes, donc l'effet sur Gemma, reste à mesurer.
- **Sortie identique en FR et EN** pour les outils non traduits (ruff, mypy, eslint, go, cargo, docker, nginx). La moitié FR diffère alors par le prompt, pas par la sortie, comme en R2-C4 p2.
- **35 % de fichiers inventés** (628 sur 1 779), écrits par l'agent : noms, montants et messages en français plus réguliers que dans la vie réelle.
- **Une seule machine**, une seule racine Debian, dates réelles du 2026-09-30 dans les sorties.
- **Docker sans démon** : seuls le client, `compose config` et les erreurs de connexion sont réels.
- **`ping` échoue toujours** faute de capacité réseau dans l'espace de noms ; `sshd -D` a dépassé son délai (retiré).
- **Mutation neutre** : quelques pannes annoncées ne changent pas la sortie (mypy sans erreur sur un retour neutralisé, cargo check sans avertissement) ; le champ `fault` décrit la préparation, pas l'effet.
- **Filtre lancé sur le Mac** : script de 4 s, 30 Mo, parce que la liste de noms de `audit_pii` n'existe que là. Les sorties publiques ont circulé RTX 3060 vers Mac ; aucune donnée personnelle n'a bougé.

## Emplacements

| Machine | Chemin | Contenu |
|---|---|---|
| dépôt | `bench/matrix/results/g3c/data/public_g3c.retained.jsonl` | **1 779 sorties retenues**, sha256 `8aa75805ce6d…` |
| dépôt | `bench/matrix/results/g3c/data/` | chaîne complète, `sources.json`, `filter_summary.json`, `stats.json`, `leak_scan_v3.json` |
| RTX 3060 | `/mnt/backup-hdd/stephbench-tmp/g3c/raw.jsonl` | 2 900 exécutions brutes, sha256 `4308a53a84c9…` ; hors dépôt (quasi-doublons du banc, 25 trouvailles PII) |
| RTX 3060 | `/mnt/backup-hdd/stephbench-tmp/g3c/{rootfs,src,tpl}` | racine (3,0 Go), sources (1,1 Go), gabarit (141 Mo), pour régénérer ; à supprimer après l'étiquetage si la place manque (disque à 95 %) |

Champs d'une ligne : `cmd`, `family`, `source`, `source_license`, `fault`, `cwd`, `docker_mode`, `scenario`, `lang`, `locale`, `exit`, `duration`, `output`, `machine`.

## Niveau de preuve

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| 1 779 sorties, FR 883, EN 896 | VÉRIFIÉ | `data/stats.json` ; `stats_g3c.py` | utilité pour l'entraînement : rien d'étiqueté ni d'entraîné |
| Contamination 0 contre le banc v3 entier | VÉRIFIÉ | `leak_check.py drop` : 0 retirée ; `leak_scan_v3.json` : 0 rejet | quasi-doublons sémantiques sans ligne commune |
| PII 0 | VÉRIFIÉ | `audit_pii.py public_g3c.retained.jsonl` : 0 | noms d'auteurs de dépôts dans les fichiers LICENSE (publics) |
| Sans réseau à l'exécution | EXÉCUTÉ | `ip -br a` : `lo` seul ; `curl` : « Could not resolve host » | aucun contrôle automatique par exécution |
| Licences notées | VÉRIFIÉ | `data/sources.json`, licence lue dans chaque archive | licence de chaque fichier de données interne aux dépôts |
| Pannes injectées réelles | EXÉCUTÉ | pilote de 98 exécutions relu ; échantillon de 16 sorties relu après génération | effet de chaque panne non vérifié une à une |
