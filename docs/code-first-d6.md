# D6 : dire plus en code, par famille de commandes

Analyse du split **dev** du banc v3 aligné L5. Aucun cas ni sortie du split test n'a été lu.
Aucune réponse de modèle n'a été lue : seules les notes par ligne de `score_production.py` servent.
Pistes 1 et 2 de l'état des lieux du 2026-10-01 : part dite en code de ~40 % à ~60 %, gabarits par famille.

## 0. Références et matière

| Élément | Valeur |
|---|---|
| Harnais | affiné L5 `harness/dev.json` (`8c686025`) pour v1.0 ; générique L5 `generic_harness.py dev` (`e96d54d4`, identique au README) pour Gemma |
| v1.0 | sorties G5 de la 3080 (`/root/steph-ft/g5/runs/v10-dev-b*.json`, même session que G5) ; non versionnées : une réponse du modèle y cite un domaine que `audit_pii.py` refuse |
| Gemma | **Gemma 4 E2B brut avec bloc L5** (`results/aids-input/runs/gemma-facts-dev-b*.json`) : substitut de G3b |
| G3b dev | **n'existe pas** : G3b n'a tourné que sur le test. Passe dev lancée sur la 3080 (`/root/steph-ft/d6/`, graine 7, en attente de 4 Go libres derrière le juge G5) ; non intégrée ici |
| Note de production dev (3 graines) | v1.0 **58,1** (58,5 / 58,1 / 57,7) ; Gemma brut L5 **68,9** (68,9 / 68,8 / 68,9) |
| Part dite en code | **40,8 %** (350 évaluations sur 858), note des lignes dites en code 78,0 |
| Points perdus sur les lignes envoyées au modèle | v1.0 **27,9** ; Gemma L5 **20,7** (sur 100, 858 évaluations) |

G3b gagne 1,2 pt de note de production sur le brut au test (G3b.md) : les gains ci-dessous, mesurés contre le brut L5, **majorent** ceux attendus contre G3b.

Outils (`bench/matrix/results/code-first-d6/`, jetables, RIGUEUR: brouillon) :

| Fichier | Rôle |
|---|---|
| `analyze.py` | taxonomie D6 par commande (`fam`) et points perdus par famille ; sortie `families-dev.json` |
| `rules.py`, `cover.py` | détecteurs de formats documentés : couverture seule, sans phrase ; sortie `cover-dev.txt` |
| `proto.py`, `proto_run.py` | prototypes de gabarits FR et EN, notés par `score_v3.score_answer` ; sortie `proto-dev.txt` |
| `list.py` | cas dev par famille, source (code ou modèle), notes moyennes, référence |

Relance depuis `bench/matrix/v3/tools` : `python3 ../../results/code-first-d6/proto_run.py ../../results/code-first-d6/analyze.py ../../results/code-first-d6/proto.py <dev.generic.json> <D>`, où `<D>/runs/` contient les `v10-dev-b*.json` copiés de la 3080 (et `g3b-dev-b*.json` s'ils existent, ajoutés d'office en colonne).

## 1. Familles classées par points perdus

Taxonomie D6 : par commande réelle (après `sudo`, `npx`, `runuser -- `), pas par famille du banc. `npm test` va en tests, `npm install` en paquets.
Points perdus : somme de (1 - note) sur les lignes envoyées au modèle, moyenne des 3 graines, en points de note sur 858.

| Famille D6 | Cas | Évaluations | Dites en code | Au modèle | Perdus v1.0 | Perdus Gemma L5 | Perdus sur les lignes de code | Fréquence réelle (`DESIGN.md`) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| files (ls, grep, diff, tar, rm/mkdir/chmod -v, sommes de contrôle) | 48 | 96 | 28 | 68 | **5,44** | **5,31** | 0,56 | haute : Greenberg, NL2Bash ; cible 40 + 12 |
| scripts (bash, ./x.sh) | 32 | 64 | 4 | 60 | **4,44** | **2,97** | 0,00 | basse : cible 15, **banc à 81 cas** (L14, L15 synthétiques) |
| packages (apt, dpkg, brew, pip, uv, npm, pnpm, poetry) | 51 | 102 | 48 | 54 | 2,88 | 2,26 | 0,66 | haute : npm, pip, Homebrew, apt en tête SO 2024 |
| tests (pytest, unittest, jest, vitest, go test, cargo test, node --test) | 41 | 82 | 58 | 24 | 2,06 | 1,68 | **1,90** | haute : cible 40 |
| network (curl, wget, ping, ip, ss, dig, nmcli, ssh) | 25 | 50 | 20 | 30 | 1,75 | 1,09 | 0,95 | haute : cible 30 + 25 |
| lint-type (ruff, pylint, eslint, tsc, shellcheck, yamllint) | 18 | 36 | 12 | 24 | 1,73 | 1,02 | 0,75 | moyenne : cible 20 |
| compile (gcc, clang, cargo build/run/clippy, go run/mod) | 17 | 34 | 12 | 22 | 1,34 | 1,17 | 0,58 | moyenne : cible 30 + 20 avec make |
| git (git, gh) | 20 | 40 | 20 | 20 | 1,54 | 0,75 | 0,41 | **universelle** : 94 % (SO 2022) |
| make-autotools (make, ./configure) | 35 | 70 | 48 | 22 | 1,00 | 1,22 | 1,09 | haute : Greenberg |
| resources (df, du, free, top, ps, lsof, vmstat) | 22 | 44 | 28 | 16 | 1,43 | 0,69 | 0,68 | moyenne : cible 25 + 20 |
| other (capteurs, lspci, openssl, route) | 23 | 46 | 26 | 20 | 1,08 | 0,60 | 0,80 | - |
| containers (docker, kubectl, helm) | 10 | 20 | 8 | 12 | 0,71 | 0,65 | 0,17 | haute : Docker en tête SO 2024 ; banc sous la cible |
| runtime (python, node, deno hors tests) | 16 | 32 | 18 | 14 | 0,72 | 0,41 | 0,23 | haute |
| db (psql, sqlite3, redis-cli) | 11 | 22 | 8 | 14 | 0,66 | 0,44 | 0,06 | moyenne : cible 20 |
| services (systemctl, journalctl, brew services) | 10 | 20 | 10 | 10 | 0,60 | 0,21 | 0,12 | moyenne : cible 30 |
| infra (terraform) | 5 | 10 | 2 | 8 | 0,52 | 0,23 | 0,00 | basse : cible 8 |
| questions (history-qa) | 45 | 90 | 0 | 90 | - | - | - | hors piste : toujours au modèle |

Constats :

- **files et scripts** concentrent 9,9 pts de v1.0 et 8,3 de Gemma, soit 36 % et 40 % du total perdu. Le poids de scripts vient du banc, pas de l'usage : 81 cas pour une cible de 15.
- **tests** perd plus sur ses lignes déjà dites en code (1,90) que sur ses lignes du modèle (1,68) : `go test -v` avec sous-tests, `pytest -v -rs`, `cargo test` d'intégration, dits vrais mais incomplets.
- Le bloc de faits L5 seul, dit tel quel en code, ne gagne rien : v1.0 +1,2, Gemma **-2,2** sur les 162 lignes où il existe (`analyze.py`, colonne `facts_proto_gain`). Il faut des gabarits par famille, pas une lecture du bloc.

## 2. Ce que le code peut dire de sûr, par règle

Prototype : phrase construite en code, statut en tête, notée comme une réponse. « Hybride » : gabarit en code suivi de la réponse du modèle, pénalité de longueur comprise ; il estime le mode de la piste 2 où le modèle ne donne que l'explication.
Gain : écart de note de production sur 858, moyenne des 3 graines. **Dans l'échantillon** : les formats viennent des documentations, mais les phrases ont été relues contre les références dev.

| Lot | Règle (format documenté) | Évaluations | Note du gabarit | v1.0 | Gemma L5 | Gemma hybride | Mieux / moins bien (Gemma) |
|---|---|---:|---:|---:|---:|---:|---|
| A | unittest : `Ran N tests`, `OK` ou `FAILED (failures=a, errors=b)`, premier `FAIL:` (doc Python `unittest`) | 12 | 0,67 | **+0,62** | **+0,57** | +0,53 | 10 / 1 |
| A | ruff : `Found N errors.`, `[*] N fixable`, fichier le plus cité (doc ruff) | 10 | **0,90** | **+0,73** | +0,30 | +0,14 | 8 / 0 |
| A | go test : lignes `ok`, `FAIL`, `? [no test files]` par paquet (`go help test`) | 6 | 0,67 | +0,31 | +0,14 | +0,29 | 3 / 2 |
| A | cargo : `Finished … in Ns`, `generated N warnings` (doc cargo) | 6 | 0,44 | +0,12 | +0,16 | +0,13 | 3 / 1 |
| A | panique Rust : `panicked at f.rs:L:C` puis message | 4 | 0,80 | +0,15 | -0,03 | -0,03 | 2 / 2 |
| A | pylint : `Your code has been rated at X/10` | 2 | 0,50 | +0,10 | +0,06 | +0,05 | 1 / 0 |
| A | node --test : `ℹ tests N`, `ℹ fail N`, premier `✖` (doc Node `node:test`) | 10 | 0,20 | -0,33 | **-0,60** | -0,45 | 0 / 7 |
| B | erreur de script : dernière ligne `script: line N: msg` ou `outil: msg` GNU (format de bash, coreutils) | 32 | 0,54 | **+0,80** | 0,00 | -0,03 | 4 / 5 |
| B | sorties verbeuses comptées : `removed '…'`, `created directory`, `creating file`, `mode of … changed` et leurs traductions | 10 | 0,60 | +0,45 | +0,41 | **+0,56** | 7 / 2 |
| B | `shred -v` : fichiers `removed` comptés | 2 | 1,00 | +0,23 | +0,23 | +0,23 | 2 / 0 |
| C | npm, pnpm : `added N packages`, `N vulnerabilities (…)` (doc npm) | 8 | 0,67 | +0,14 | -0,01 | +0,13 | 2 / 2 |
| C | terraform : `Apply complete! Resources:`, `Plan:`, `No changes.`, `successfully initialized` | 6 | 0,44 | +0,02 | -0,22 | +0,02 | 1 / 4 |
| D | wget : `Downloaded: N files, S`, `ERROR NNN` (manuel GNU Wget) | 8 | 0,75 | +0,43 | +0,17 | **+0,41** | 2 / 1 |
| D | curl `-i`, `-v`, `-I` : dernière ligne de statut `HTTP/x NNN` | 4 | 0,25 | -0,06 | -0,06 | +0,06 | 0 / 1 |
| | **Ensemble des prototypes** | **120** | | **+3,70** | **+1,13** | | part en code 40,8 -> **54,8 %** |

Détecteurs sans phrase (`rules.py`, couverture seule) sur les autres règles candidates, gain si le gabarit atteignait 0,78 (note actuelle des lignes de code) ou 0,60 :

| Lot | Règles | Évaluations couvertes (avec les prototypes) | v1.0 à 0,78 / 0,60 | Gemma à 0,78 / 0,60 |
|---|---|---:|---|---|
| A | + gcc et clang réussis avec avertissements, `Undefined symbols`, panique Go et interblocage, `Found N errors in M files` (tsc, mypy), shellcheck `In f line N`, yamllint, deno, jest `No tests found`, erreur de configuration ruff ou eslint | 76 | +3,55 / +1,96 | +1,92 / +0,33 |
| B | + `grep -r` compté (sans tube), `diff -rq` (`differ`, `Only in`), `wc` avec total, bilan rsync | 86 | +4,62 / +2,81 | +2,81 / +1,00 |
| C | + `git branch` (branche courante, compte), `fatal:` en échec, `HEAD is now at`, rebase en cours, `git log --stat`, `apt list --upgradable`, `dpkg -l` (`ii`), `apt-cache policy`, listes brew et pip comptées, `uv Resolved/Installed`, `ERROR:` de pip, docker `failed to solve`, kubectl `Unable to connect`, helm `chart(s) linted`, `terraform state list` | 80 | +2,80 / +1,12 | +1,17 / **-0,51** |
| D | + `ss -l`, `ip route` (`default via`), `nmcli`, en-tête de `top -b`, `memory_pressure`, `vmstat -s`, `du -c`, `lsof`, `diskutil info`, `smartctl -H`, `systemctl list-timers` et `is-enabled`, `brew services list`, `psql: error:`, `FATAL: database … does not exist`, `(N rows)`, sqlite `Parse error` | 52 | +2,10 / +1,01 | +0,64 / **-0,45** |
| | **Plafond de couverture** | 294 | | part en code 40,8 -> 75,1 % |

Lecture :

- **v1.0 gagne partout** : un gabarit exact bat ce modèle presque toujours.
- **Gemma ne gagne que là où le gabarit est complet** : compteurs de tests (unittest), ruff, sorties verbeuses, téléchargements. Ailleurs, un gabarit à 0,60 lui coûte des points : C et D ne passent en code seul que règle par règle, avec abstention.
- **L'hybride sauve les gabarits incomplets** (npm, terraform, wget, curl, go test) : le code dit le squelette exact, le modèle ajoute la cause. Il perd sur ruff (+0,30 -> +0,14) où la phrase de code suffit et où l'ajout du modèle dépasse 20 mots.
- **node --test en code seul est à proscrire** : le compte et le premier test sont justes, mais le fait utile est l'assertion (attendu, obtenu) que seul le modèle reformule. Mode hybride, ou rien.
- **scripts en code seul ne gagne rien à Gemma** (4 mieux, 5 moins bien) : la dernière erreur est juste, mais le bilan de progression (« 82 éléments synchronisés, puis ») manque. Hybride ou abstention.

## 3. Relecture à la main des phrases prototypes

Les 120 phrases de `proto-dev.txt` relues une à une. **Aucune fausse.** Défauts d'exactitude ou de lecture trouvés, à régler avant toute règle de production :

| Défaut | Exemple dev | Règle à poser |
|---|---|---|
| Espaces insécables des traductions gettext : `Téléchargés\xa0: 4\xa0fichiers` ; le prototype wget ne voyait **aucune** sortie française | `v3-network-transfer-0037` | toute regex FR accepte `[ \xa0]` autour des deux-points et entre nombre et unité ; un test par règle avec la sortie française |
| Dernière erreur d'outil sans la cause : `tar: Error is not recoverable: exiting now` au lieu de `Unexpected EOF in archive` | `v3-shell-scripts-0013` | pour tar et les outils qui concluent par une ligne générique, prendre la première ligne du dernier bloc d'erreurs |
| Plusieurs échecs du même outil, un seul dit | `v3-shell-scripts-0005` (2 `cp` en échec) | dire « 2 erreurs de cp, dont … » quand l'outil échoue plusieurs fois |
| Message d'exception coupé au milieu d'un mot (« messa. ») | `v3-rust-go-0011` | couper aux mots (`_clean` de `digest.py`), jamais aux caractères |
| Message en français lu dans une phrase anglaise (sortie en locale `fr_FR`) | `v3-shell-scripts-0022@en` | langue de la sortie différente de la session : garder le fichier et la ligne, laisser le message au modèle (mode hybride) |
| `go test -cover` : paquet à 0 % de couverture ni `ok` ni `?`, omis | `v3-tests-0055` | avec `-cover`, dire la couverture ou s'abstenir |
| Accords : « 1 tests », « 1 erreurs », « 1 critiques » | `v3-tests-0017`, `v3-js-node-0011` | `_n()` de `digest.py` pour chaque compteur |
| unittest : « Premier » est le premier du rapport final, pas de l'exécution | `v3-tests-0016` | dire « par exemple » ou suivre l'ordre des lignes `... FAIL` |

Pièges déjà connus et à garder : ne jamais compter les lignes `warning:` d'un compilateur (L2) ; `grep` est un visualiseur dans `resolve()` (seul son échec se résout aujourd'hui) ; un tube vers `head` ou `tail` tronque tout compte.

## 4. Lots indépendants

Chaque lot est une branche et un worktree. Code en anglais, chaînes FR et EN dans `strings.py`, TDD strict, une sortie publique ou documentée par règle, provenance notée dans le test.
Entrée du modèle inchangée : tout est `code_answer` ou post-traitement. Le mode hybride change ce qui est dit, pas l'entrée ; il passe derrière un réglage désactivé tant qu'il n'est pas mesuré.

| Lot | Familles | Fonctions touchées (`src/steph/digest.py` sauf mention) | Tests | Gain prototypé v1.0 / Gemma | Plafond (0,78) v1.0 / Gemma | Part en code (seul) |
|---|---|---|---|---|---|---|
| **A** tests, lint, compilation | tests, lint-type, compile ; lignes de code de tests (1,90 pt perdu) | `_tests` (unittest, go test par paquet, `-cover`, node --test en hybride), nouvelle `_lint` (ruff, pylint, tsc, mypy, shellcheck, yamllint) à côté de `_eslint`, `_compile` et `_go` (cargo `Finished`, clippy, paniques Rust et Go) | `tests/test_digest_d6_a.py` | +1,70 / +0,59 | +3,55 / +1,92 | +50 à +76 évaluations |
| **B** scripts, fichiers | scripts, files | nouvelles `_script_error`, `_verbose_count`, `_checksum`, `_grep_count`, `_diff_brief` ; `_file_error` inchangée | `tests/test_digest_d6_b.py` | +1,48 / +0,64 | +4,62 / +2,81 | +44 à +86 |
| **C** paquets, git, conteneurs, infra | packages, git, containers, infra | `_apt` (list, policy), `_pip` (uv, liste), `_node_error` ou nouvelle `_npm`, `_git` (branch, fatal, rebase, log --stat), `_containers` (buildkit, kubectl, helm), nouvelle `_terraform` | `tests/test_digest_d6_c.py` | +0,16 / -0,23 (hybride +0,56 / +0,15) | +2,80 / +1,17 | +14 à +80 |
| **D** réseau, ressources, services, bases | network, resources, services, db | `_net` (wget, statut curl, ss, ip route), `_system` et `_process` (top, memory_pressure, vmstat, lsof, diskutil, smartctl), nouvelles `_services` et `_db` | `tests/test_digest_d6_d.py` | +0,37 / +0,12 (hybride +0,70 / +0,47) | +2,10 / +0,64 | +12 à +52 |
| Mode hybride (piste 2) | toutes | `narrator._finish` et `_llm_say` : gabarit dit en code, puis la réponse du modèle, statut et doublons retirés ; réglage `code_skeleton`, faux par défaut ; `score_production.py` le rejoue | `tests/test_narrator.py` | voir colonnes hybrides | - | - |

Points de conflit, seuls fichiers partagés :

- le tuple `families` de `resolve()` : une ligne par lot ; ordre imposé `_tests`, `_lint` (A), `_script_error`, `_verbose_count` (B) avant `_file_error`, puis les familles existantes ;
- `strings.py` : clés préfixées par lot (`resolve.d6a.*`, `resolve.d6b.*`…), chaque lot écrit son bloc FR et son bloc EN juste après les clés `resolve.` existantes de sa famille ;
- fusion dans l'ordre A, B, C, D, suite `tests/test_digest*.py` rejouée après chaque fusion ; renommer toute regex de module en doublon (piège de la fusion D5 : `_CONFIGURE_ERROR` écrasé).

Ordre recommandé : **A** (meilleur gain pour Gemma, familles fréquentes), **B** (plus gros gisement, mais poids de scripts propre au banc), **D** (fréquence réelle haute, gabarits surtout hybrides), **C** (git universel, mais code seul négatif pour Gemma hors npm et listes).

## 5. Atteindre 60 %

| Palier | Évaluations dites en code | Part |
|---|---:|---:|
| Aujourd'hui (L1 à L5) | 350 | 40,8 % |
| Prototypes des quatre lots | 470 | 54,8 % |
| + 30 % des 174 autres évaluations détectées (le reste en abstention ou en hybride) | environ 520 | **environ 60 %** |
| Plafond de couverture des détecteurs | 644 | 75,1 % |

Les 60 % se tiennent avec le code seul là où le gabarit est complet, l'hybride ailleurs. Au-delà, le code seul coûte des points à Gemma et G3b.

## 6. Limites

| Limite | Effet |
|---|---|
| G3b absent du dev ; Gemma brut L5 en substitut | gains Gemma majorés d'au plus la marge G3b-brut (1,2 pt au test) ; à remesurer sur `g3b-dev-b7.json` quand la passe 3080 aura tourné |
| Gains dans l'échantillon, phrases relues contre les références dev | le test, lu une fois à l'intégration, donnera moins (D5 : environ 25 % de moins) |
| Hybride estimé par simple concaténation | la production doit retirer les doublons (compteurs redits par le modèle) ; l'écoute n'est pas mesurée |
| Poids du banc : scripts 81 cas, tests 121, `apt-get -s` 36 | un gain sur ces familles pèse plus dans la note que dans l'usage |
| Détecteurs sans phrase | le plafond suppose une phrase à 0,78 ou 0,60 ; seuls les 120 prototypes ont une note réelle |
| Jamais entendu en synthèse vocale | lisibilité orale des gabarits non vérifiée (chiffres, virgules décimales, noms de fichiers) |

## 7. Lot A écrit (branche `d6/A`)

Code : `src/steph/digest.py` (`_tests`, nouvelle `_lint`, `_compile`, `_go`), `src/steph/strings.py` (clés `resolve.d6a.*`), tests `tests/test_digest_d6_a.py` (67 tests, provenance notée par groupe). Entrée du modèle inchangée : `tools/test_l5_production.py` vert.

| Règle | Source du format | Code seul ou abstention |
|---|---|---|
| unittest : échecs, erreurs, total, un test nommé avec fichier et ligne, exception d'un ERROR ; import en échec (`_FailedTest`) | doc Python `unittest` | abstention : clés inconnues (`expected failures`), total omis sous `subTest` |
| go test : paquets réussis, sans tests, couverture ; échec : feuilles comptées, journal attribué au bon test | `go help test`, `go help testflag` | abstention : `-json`, tube, `[no tests to run]`, tests parallèles (pas de message) |
| paniques Go (interblocage compris) et Rust (`unwrap` sur `io::Error`) | runtime Go, std Rust | panique pendant `go test` : le test en échec est dit, pas la pile |
| deno, Jest « No tests found », couverture Istanbul `% Lines` | manuel Deno, Jest, Istanbul | - |
| pytest : type et message court de l'exception, délai pytest-timeout, premier échec lu sur `-v` | doc pytest, pytest-timeout | message au-delà de 6 mots ou avec opérateurs : type seul ; phrase plafonnée à 20 mots |
| cargo test : `left`, `right` d'`assert_eq!` | std Rust | valeurs structurées non lues |
| ruff (compte, fichier, corrigeables, configuration invalide), pylint, ShellCheck, yamllint, mypy, ESLint sans configuration, avertissements d'ESLint | docs ruff, pylint, ShellCheck, yamllint, mypy, ESLint 9 | fichier nommé seulement si chaque erreur annoncée a sa ligne |
| cargo build, check, clippy réussis ; échec Rust avec avertissements émis ; tsc « in M files » | cargo, tsc | plusieurs résumés « generated N warnings » : pas de somme |
| gcc, clang réussis avec avertissements ; ld64 `Undefined symbols` | manuels GCC, Clang, ld64 | jamais de compte gcc (L2) ; message français tu en session anglaise |
| tous les tests passent mais la commande échoue : « Échec. » en tête | Jest (seuil de couverture), Vitest (suite en échec) | - |

Garde-fou ajouté après relecture : toute commande enchaînée (`&&`, `;`, `||`, tube) reste au modèle pour les nouvelles règles. Sans lui, `gcc … && ./stats` taisait la sortie du programme (`v3-build-native-0001`).

Défaut préexistant corrigé : en `go test -v`, `resolve()` lisait le journal du test **suivant** (« TestBilling02, Len = 15, want 16 » au lieu de « Len = 2, want 3 », `v3-tests-0094`). Phrase fausse, dite en code avant ce lot.

Mesure hors ligne dev (3 graines, `score_production.py`, sorties existantes) :

| Modèle | Avant | Après | Écart | Part en code |
|---|---|---|---:|---|
| v1.0 (harnais affiné L5) | 58,5 / 58,1 / 57,7 | 63,8 / 63,2 / 63,2 | **+5,3** | 40,8 -> 48,0 % |
| Gemma brut L5 (substitut G3b) | 68,9 / 68,8 / 68,9 | 73,0 / 72,7 / 73,1 | **+4,1** | 40,8 -> 48,0 % |
| G3b (harnais générique L5, 3080, `/root/steph-ft/d6/runs/g3b-dev-b*.json`) | 69,7 / 69,4 / 69,4 | 73,8 / 73,6 / 73,7 | **+4,2** | 40,8 -> 48,0 % |

- 108 évaluations changées (54 cas) : 78 mieux et 2 moins bien chez v1.0, 74 mieux et 2 moins bien chez Gemma, 74 mieux et 0 moins bien chez G3b. Par famille : tests +2,60 / +2,34, lint-type +1,37 / +0,83, compile +1,26 / +0,90.
- Moins bien : `v3-build-native-0047@en` (compte gcc tu par règle, message coupé à 20 mots) et `v3-lint-format-0012` (ShellCheck ne dit que la première remarque). Phrases vraies.
- **Relues à la main** : les 108 phrases dev changées et 168 phrases changées sur les corpus publics (`fixtures.json`, `extra_fixtures.json`, `public_t7`, `public_p1`). **0 phrase fausse** après le garde-fou d'enchaînement.
- Écart avec le prototype (+1,70 / +0,59) : le lot couvre plus de règles que les 7 prototypées et corrige 30 lignes de tests déjà dites en code.
- Cas du banc contestables, non visés : `v3-tests-0063` interdit « passed » alors que 56 tests passent ; `v3-tests-0113` interdit le premier échec réel (`parse_16`) ; `v3-tests-0048` interdit le total juste de cargo (7).
- Hors lot : node --test reste au modèle (le mode hybride, piste 2, n'existe pas encore).

## 8. Lots B, C et D

| Lot | Branche | Familles | Détail |
|---|---|---|---|
| B | `d6/B` | scripts bash, outils GNU seuls, sorties verbeuses, sommes de contrôle, grep, diff, wc, rsync | `bench/matrix/results/code-first-d6/lot-b/README.md` |
| C | `d6/C` | npm et pnpm, pip, uv et poetry, apt, dpkg et brew, git et gh, BuildKit, kubectl, helm, Terraform ; gabarit `skeleton()` écrit, non branché | `docs/code-first-d6-c.md` |
| D | `d6/D` | wget, curl, ss, ip route, nmcli, TLS, SSH ; top, vmstat, du, lsof, diskutil, smartctl ; systemctl, brew services ; psql, sqlite | `tests/test_digest_d6_d.py` (provenance par groupe) |

## 9. Intégration des lots A à D (branche `d6/integration`, fusionnée sur master)

### Conflits résolus

| Conflit | Résolution |
|---|---|
| `_CHAINED` défini par A et par B, regex différentes : la seconde écrasait la première | B renommé `_SHELL_CHAINED` ; chaque lot garde son garde-fou |
| `_short_path` défini par A et par B, sémantique différente | celui de A renommé `_ruff_path` |
| `_join` défini par A, C et D, même phrase | un seul, avec le séparateur optionnel de D ; liste vide rendue vide |
| `_capped` défini par C et D, signatures différentes | celui de D renommé `_capped_list` |
| `du -c` en échec pris par `_script_error` (B) avant le total de D | petite famille `_du` placée avant `_script_error` ; les 2 tests de D repassent |
| `test_l5_production` exigeait plus de 300 entrées comparées | 147 entrées DEV atteignent encore le modèle : seuil abaissé à 120 |

Contrôle croisé : `resolve()` rejoué avec master, chaque lot et la fusion sur les cas DEV et les corpus publics (2 412 entrées). 565 phrases changent ; chacune est changée par un seul lot et la fusion rend exactement la phrase de ce lot. Aucune phrase changée par la seule fusion, aucune exception.

Entrée du modèle inchangée : harnais générique DEV et TEST régénérés avec master et avec la fusion, empreintes identiques ; celui du TEST est aussi identique au harnais des runs G3b de la 3080.

### Mesure DEV (3 graines, `integration/measure.py`, dans l'échantillon)

| Modèle | Avant | Après | Écart apparié [IC95] | Mieux / moins bien |
|---|---|---|---|---|
| G3b | 69,7 / 69,4 / 69,4 | 82,7 / 82,7 / 82,9 | **+13,2 [+10,8 ; +15,7]** | 216 / 3 |
| v1.0 | 58,5 / 58,1 / 57,7 | 77,9 / 77,1 / 77,1 | **+19,2 [+16,3 ; +22,2]** | 257 / 4 |

Part dite en code 40,8 -> **72,4 %** ; note des lignes dites en code 78,0 -> 87,2 ; 325 phrases de code changées.

Relecture : 40 phrases changées tirées au hasard, relues contre la sortie brute, comptes cachés recomptés par script. **0 fausse sur 40** (`integration/review-40.md`). Une phrase repose sur une convention : vmstat en Kio dit « Go », comme free.

### Mesure TEST (lue une seule fois, aligné L5, runs G3b et v1.0 de la 3080)

| Modèle | Avant | Après | Écart apparié [IC95] | Mieux / moins bien |
|---|---|---|---|---|
| G3b | 68,4 / 69,0 / 68,9 (68,8) | 72,2 / 72,5 / 72,4 (72,4) | **+3,60 [+2,18 ; +5,04]** | 128 / 38 |
| v1.0 | 58,5 / 59,0 / 59,2 (58,9) | 65,2 / 65,5 / 65,8 (65,5) | **+6,59 [+4,93 ; +8,35]** | 165 / 28 |

Part dite en code 40,5 -> **57,7 %** ; 293 phrases de code changées. Note des lignes dites en code 78,6 -> 78,0 : les nouvelles lignes de code valent à peu près les anciennes, le gain vient de lignes que le modèle disait moins bien. Bootstrap apparié par cas (`power_v3.compare`, 654 cas, moyenne des 3 graines).

Le gain TEST vaut 27 % du gain DEV pour G3b et 34 % pour v1.0 : les règles ont été écrites en lisant les sorties DEV, l'écart attendu en D5 était d'environ 25 %. Les phrases TEST n'ont pas été lues ; les 38 évaluations moins bien de G3b ne sont pas examinées, pour ne pas écrire de règle contre le TEST.

### Limites

| Point | État |
|---|---|
| Phrases fausses au TEST | non vérifié : aucune phrase TEST lue, par règle |
| Mode hybride (gabarit du code, explication du modèle) | `skeleton()` écrit, jamais branché dans narrator |
| Écoute en synthèse vocale | personne n'a entendu ces phrases |
| Objectif 60 % | 57,7 % au TEST, 72,4 % au DEV |
