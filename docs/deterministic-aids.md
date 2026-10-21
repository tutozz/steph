# Aides déterministes : note de production et leviers

Analyse sur le split **dev** du banc v3 seulement. Aucune réponse de modèle du split test n'a été lue.
Aucun modèle n'a tourné : toutes les mesures rescorent les sorties déjà produites (`bench/matrix/results/v3-rescore/runs/*-dev-b*.json`).
Sections 1 à 3 : analyse et prototypes hors ligne. Section 4 : L1 à L5 écrits en TDD et fusionnés sur master ; mesure finale sur le split **test**, lue une seule fois.

## 1. Note composite de production

Outil : `bench/matrix/v3/tools/score_production.py` (tests : `test_score_production.py`, 13 tests).
Par ligne du banc, il rejoue `narrator._finish` et `server._ask` avec la configuration par défaut :

- sortie vide, code 127, sortie courte lue telle quelle (20 mots, 3 lignes non vides), `resolve()` : **la phrase du code**, la réponse du modèle est ignorée ;
- sinon la réponse du modèle, passée par le garde-fou d'ancrage (`ground_output`, actif par défaut), statut du modèle retiré, statut dit en code en tête ; un résumé entièrement coupé par l'ancrage devient le repli construit en code ;
- questions : réponse du modèle passée par l'ancrage en mode question.

Même barème que `score_v3.py`. `--no-ground` coupe l'ancrage. `--harness` donne le harnais du run (générique pour les modèles bruts, régénéré par `generic_harness.py dev`, empreinte `247b1141`, identique à X3).
Non modélisés : règles par commande, fait de compte de lignes dit pendant la lecture du prompt, durée en suffixe des commandes longues, sessions interactives et plein écran.

| Modèle (dev) | Graine 7 | Graine 42 | Graine 123 | Sans ancrage (g. 7) | `score_v3` brut (moy. 3 graines, X3) |
|---|---:|---:|---:|---:|---:|
| v1.0 (R1) | **52,7** | 52,0 | 51,3 | 52,8 | 50,4 |
| Gemma 4 E2B brut | **58,7** | 59,4 | 59,2 | 60,7 | 60,5 |

| Part des évaluations | Valeur |
|---|---:|
| Dites en code (`resolve` et consorts) | **37,3 %** (320 sur 858) |
| dont `resolve()` | 182, note 53,5 |
| dont lecture telle quelle | 128, note 78,6 |
| dont code 127 et sortie vide | 10 |
| Note des lignes dites en code | 64,0 |
| Note des lignes du modèle | v1.0 46,0 ; Gemma 55,6 |

Constats :

- **L'ancrage coûte 2,0 pts à Gemma** (60,7 -> 58,7) et presque rien à v1.0 (-0,1). Sur les questions à réponse présente, Gemma perd 8,6 pts (85,3 -> 76,7). Cause : faux rejets du garde-fou (section 3, levier L3).
- **Sur les lignes dites en code, Gemma brut ferait aussi bien que `resolve()`** (54,3 contre 53,5) ; v1.0 ferait moins bien (44,9). `resolve()` n'aide donc que les petits modèles, et porte des défauts d'exactitude (L1).
- Écart trouvé dans `v3lib.reaches_model` : il compte les lignes vides, `narrator` non. `v3-containers-0022` et `v3-network-0019` sont lus tels quels en production mais marqués « envoyés au modèle » par le banc (4 évaluations).

## 2. Taxonomie des échecs (dev, graine 7, réponses entendues)

Classement par ordre de priorité : interdit touché, question à réponse absente manquée, recopie (au moins 50 % des mots en suites de 4 jetons copiées de la sortie), mauvaise langue (classifieur de trigrammes `lang_rate.py`), trop long, repli de l'ancrage, sinon fait clé manqué.

| Source | Modèle | n | Parfait | Partiel | Zéro | Note |
|---|---|---:|---:|---:|---:|---:|
| Modèle | v1.0 | 538 | 137 (25 %) | 224 (42 %) | 177 (33 %) | 46,0 |
| Modèle | Gemma | 538 | 198 (37 %) | 196 (36 %) | 144 (27 %) | 55,6 |
| Code | les deux | 320 | 152 (48 %) | 100 (31 %) | 68 (21 %) | 64,0 |

Points de note composite perdus sur 858, lignes du modèle :

| Type | v1.0 (lignes) | v1.0 (pts) | Gemma (lignes) | Gemma (pts) |
|---|---:|---:|---:|---:|
| Fait clé manqué | 271 | 22,5 | 236 | 19,0 |
| Mauvaise langue | 66 | 5,8 | 39 | 3,3 |
| Recopie de lignes | 34 | 2,5 | 32 | 2,0 |
| Interdit ou invention | 19 | 2,2 | 21 | 2,4 |
| Repli de l'ancrage | 2 | 0,2 | 8 | 0,8 |
| Question à réponse absente manquée | 4 | 0,5 | 2 | 0,2 |
| Trop long | 5 | 0,1 | 2 | 0,0 |
| **Total** | 401 | **33,9** | 340 | **27,8** |

La « mauvaise langue » recouvre surtout des recopies de la sortie anglaise sous prompt français : le classifieur ne sépare pas les deux.

**Le fait manqué est presque toujours dans l'entrée du modèle.** Faits exigés manqués, par emplacement :

| Modèle | Dans l'entrée du modèle | Seulement dans la sortie brute (coupé par `digest`) | Ni l'un ni l'autre (déduit, reformulé) |
|---|---:|---:|---:|
| v1.0 | 443 | 2 | 64 |
| Gemma | 379 | 0 | 55 |

Par famille (lignes du modèle ; colonnes : fait manqué, recopie, interdit, langue, trop long, absente, repli) :

| Famille | v1.0 n | v1.0 pts perdus | v1.0 détail | Gemma pts perdus | Gemma détail |
|---|---:|---:|---|---:|---|
| build-native | 58 | 4,0 | 34 / 1 / 0 / 7 / 1 / 0 / 0 | **4,7** | 36 / 2 / 2 / 7 / 0 / 0 / 0 |
| files | 54 | 4,0 | 31 / 1 / 0 / 14 / 1 / 0 / 0 | **4,5** | 32 / 5 / 3 / 7 / 0 / 0 / 3 |
| shell-scripts | 60 | 4,1 | 28 / 10 / 2 / 8 / 0 / 0 / 0 | 3,2 | 29 / 13 / 1 / 3 / 0 / 0 / 1 |
| history-qa | 90 | **4,7** | 27 / 2 / 6 / 6 / 0 / 4 / 0 | 2,3 | 14 / 1 / 3 / 3 / 0 / 2 / 0 |
| tests | 36 | 2,4 | 22 / 2 / 2 / 1 / 0 / 0 / 1 | 2,0 | 16 / 1 / 5 / 1 / 0 / 0 / 0 |
| packages-system | 24 | 1,8 | 15 / 2 / 0 / 4 / 0 / 0 / 0 | 1,5 | 9 / 0 / 3 / 4 / 0 / 0 / 2 |
| lint-format | 22 | 1,9 | 16 / 0 / 3 / 2 / 0 / 0 / 0 | 1,3 | 16 / 0 / 0 / 1 / 1 / 0 / 0 |
| network-transfer | 26 | 1,5 | 17 / 0 / 0 / 5 / 0 / 0 / 0 | 1,0 | 11 / 2 / 0 / 0 / 0 / 0 / 0 |
| js-node | 24 | 1,0 | 13 / 2 / 0 / 1 / 1 / 0 / 0 | 1,0 | 13 / 0 / 0 / 2 / 0 / 0 / 0 |
| vcs-git | 18 | 1,3 | 10 / 4 / 0 / 1 / 1 / 0 / 1 | 0,8 | 4 / 3 / 0 / 2 / 0 / 0 / 2 |
| python | 20 | 1,0 | 12 / 1 / 0 / 3 / 0 / 0 / 0 | 0,9 | 9 / 0 / 1 / 2 / 1 / 0 / 0 |
| rust-go | 14 | 0,8 | 6 / 2 / 2 / 0 / 0 / 0 / 0 | 0,9 | 11 / 0 / 0 / 0 / 0 / 0 / 0 |
| permissions-users | 12 | 1,1 | 6 / 3 / 0 / 3 / 0 / 0 / 0 | 0,9 | 9 / 1 / 0 / 0 / 0 / 0 / 0 |
| 8 autres familles | 80 | 4,3 | | 3,0 | |

Commandes qui coûtent le plus (lignes du modèle, pts perdus sur 858) : `make` v1.0 2,3, Gemma **3,0** ; `./configure` 1,1 et 1,2 ; `git` 1,3 et 0,8 ; `ruff` 1,0 et 0,6 ; `python3` (tests) 0,7 et 0,8 ; `diff` 0,4 et 0,8 ; `go test`, `brew`, `npm`, `cargo`, `grep`, `pip` entre 0,4 et 0,6 chacune.

Échecs des lignes dites en code (320) : 96 faits manqués, 46 interdits touchés, 23 lectures dans la langue de la sortie. Les 46 interdits se répartissent ainsi :

| Cause | Évaluations | Nature |
|---|---:|---|
| `apt-get -s` : `resolve()` dit « 36 paquets installés » pour une **simulation** | 26 | **phrase fausse dite à l'utilisateur** |
| Lecture telle quelle de `***` (`make: ***`, `** server can't find`), interdit global `\*\*` | 6 | bruit lu à voix haute |
| Faits du banc écrits contre l'entrée tronquée : « 7 tests passed » (cargo, 5 + 2, vrai), « 78 passed » et `test_billing_parse_16` (pytest, vrais) | 6 | **défaut du banc**, pas du code |
| `g++` : première erreur dans `stl_function.h` au lieu du fichier de l'utilisateur ; `clang-format` : 25 erreurs ; `go test` : « 1 test échoué » avec 3 sous-tests ; `ip -br addr` lu tel quel avec l'IPv6 | 8 | discutable, à relire |

Autres défauts d'exactitude relevés dans `resolve()` et la chaîne de code :

- `bash deploy.sh` en 127 dit « Commande introuvable : bash » alors que c'est `rsyncx`, ligne 7 du script (`v3-shell-scripts-0001`) ;
- `grep` en code 1 sans sortie dit « Échec, code 1, aucun message » au lieu de « aucune correspondance » (`v3-files-0004`) ;
- `pytest` en erreur de collecte dit « Premier : , test_config.py ligne 1 » (nom vide, `v3-tests-0005`) ;
- traceback Python chaîné : seule la dernière exception est dite, la cause (`KeyError 'region'`, `FileNotFoundError`) est perdue (`v3-python-0043`, `0046`, `0047`, `0052`).

Défauts du garde-fou d'ancrage (`src/steph/grounding.py`), trouvés sur les faux rejets de Gemma :

- un identifiant qui commence par un chiffre (empreinte `2cb4b14…`, version) est tronqué par `_WORD_RE` et jamais retrouvé (`v3-history-qa-0041`) ;
- un nombre composé en lettres (« Trente-six », « Forty-five ») est pris pour un identifiant à tiret (`v3-history-qa-0054`, `0056`) ;
- un point après un chiffre ne coupe pas la phrase : le mot en capitale qui suit devient un nom propre à ancrer (« … colonne 22. Format JSON invalide », `v3-history-qa-0010`) ;
- quand seule la reprise du statut survit (« Échec. »), la production ne dit que « Échec, code 1. » : le repli ne part pas (`v3-build-native-0031`, `v3-files-0082`).

## 3. Leviers classés par gain estimé

Gain = écart de note composite dev, moyenne des 3 graines, prototype appliqué aux sorties existantes. **Mesure dans l'échantillon** : les règles ont été écrites en lisant dev, le gain sur test sera plus faible. Le test ne sert qu'à la mesure finale, une fois.

| Rang | Levier | Type | Touche l'entrée ? | v1.0 | Gemma | Évaluations changées (g. 7, Gemma) |
|---|---|---|---|---:|---:|---|
| L1 | Exactitude de `resolve()` | code_answer | non | **+3,6** | **+3,6** | 42 : 36 mieux, 2 moins bien |
| L2 | Familles autotools : `./configure`, `make` réussi | code_answer | non | +1,2 | **+2,0** | 42 : 28 mieux, 6 moins bien ; part en code 37,3 -> 42,2 % |
| L3 | Faux rejets du garde-fou d'ancrage | post_process | non | -0,2 | +1,0 | 32 : 14 mieux, 1 moins bien |
| L4 | Symboles retirés de la lecture telle quelle | code_answer | non | +0,6 | +0,6 | 12 |
| L5 | Bloc de faits extraits en code dans l'entrée | input_change | **oui** | non mesuré | non mesuré | - |
| L6 | Coupe à `max_words` sur une frontière de proposition | post_process | non | 0,0 | +0,2 | 23 réponses trop longues |
| **L1 à L3 ensemble** | | | | **+4,6** (52,0 -> 56,6) | **+6,5** (59,1 -> 65,6) | 114 : 76 mieux, 9 moins bien |

### L1. Exactitude de `resolve()` (code_answer)

- **Fichiers** : `src/steph/digest.py` (`_apt`, `_tests`, `_traceback`, nouvelle famille `grep`), `src/steph/narrator.py` (branche 127), `src/steph/strings.py`, `tests/test_digest.py`.
- **Règles** :
  - `apt`/`apt-get` avec `-s`, `--simulate`, `--dry-run`, `--just-print`, `--no-act` : « Simulation seulement : {paquet} serait installé avec ses dépendances », jamais « installés ». Source : sémantique de `apt-get(8)`, exemple dev `v3-packages-system-0047`.
  - Code 127 sous un interpréteur ou un script : nom et ligne lus dans `line N: X: command not found` / `ligne N : X : commande introuvable`. Source : format d'erreur de bash, exemple dev `v3-shell-scripts-0001`.
  - `grep`, `rg` en code 1 sans sortie : « Aucune correspondance pour {motif} ». Source : code de sortie POSIX de grep, exemple dev `v3-files-0004`.
  - Traceback chaîné (`During handling of the above exception`, `direct cause`) : cause d'origine avec fichier et ligne, puis exception finale. Source : documentation Python, exemple dev `v3-python-0043`.
  - `pytest` en erreur de collecte : pas de « Premier : » à nom vide. Exemple dev `v3-tests-0005`.
- **Preuve** : 26 évaluations `apt-get -s` à 0 disent une installation fausse ; 4 tracebacks perdent la cause ; 1 script 127 nomme le mauvais programme.
- **Risque relevé** : le traceback chaîné allonge la phrase (`v3-python-0036` passe de 1 à 0). Garder la cause seulement si la phrase tient dans 20 mots.
- **Gain estimé** : +3,6 pts, dont environ +3,0 pour `apt-get -s` seul. Le banc a 36 cas `apt-get -s` sur 1 083 : ce poids est propre au banc, le défaut d'exactitude est réel partout.
- **État : écrit en TDD sur la branche `aids/L1`**, actif par défaut, entrée du modèle inchangée. Fonctions `not_found_sentence` et `grep_no_match` dans `digest.py`, rejouées par `score_production.py`.

| Mesure dev (hors ligne, sorties existantes) | v1.0 g. 7 / 42 / 123 | Gemma g. 7 / 42 / 123 |
|---|---:|---:|
| Avant | 52,7 / 52,0 / 51,3 | 58,7 / 59,4 / 59,2 |
| Après | **56,8 / 56,1 / 55,5** | **62,8 / 63,5 / 63,4** |

- 43 évaluations changées par graine et par modèle (lignes dites en code, identiques d'un modèle à l'autre) : 42 mieux, 1 moins bien, **0 phrase devenue fausse** (les 43 relues).
- Seule baisse : `v3-python-0036@en`, phrase vraie (« ValueError … puis RuntimeError bad row 59 ») notée 0 par un interdit du banc qui prend `ValueError` pour une invention alors qu'il est dans la sortie. En français la phrase dépasse 20 mots et garde l'exception finale seule.
- Corpus publics (`public_t7`, `public_p1`, `bench/fixtures.json`) : 20 phrases changées, toutes relues et vraies (`pnpm` au lieu de `npm` dans un script npm, `dot` au lieu de `systemd-analyze` dans un tube, erreurs de collecte pytest nommées).
- Pièges : `[Errno 2]` reste lu dans les messages d'exception ; une erreur de collecte pytest sans ligne `E` ne donne que le fichier ; pour `apt-get -s install`, les mises à jour de dépendances ne sont pas dites (« avec ses dépendances » les couvre).

### L2. Familles autotools (code_answer)

- **Fichiers** : `src/steph/digest.py` (familles `_configure`, `_make`), `src/steph/strings.py`, tests.
- **Règles** :
  - `./configure` réussi avec des lignes `config.status: creating Makefile` et `config.h` : « Configuration réussie, Makefile et config.h générés ». Source : sortie standard d'autoconf, exemples dev `v3-build-native-0056` et `0061`.
  - `./configure` en échec : dernière ligne `configure: error:` qui ne commence pas par `in '…'`. Exemple dev `v3-build-native-0091`.
  - `make` en code 0, hors `test`, `check`, `-n`, sans ligne `error:` ni `*** [` : projet et version lus dans le plus court `make[1]: Entering directory` (anglais et français), puis « aucune erreur ni avertissement » ou le premier fichier averti. Source : messages de GNU make, exemples dev `v3-build-native-0070` et `0073`.
- **Preuve** : `make` et `./configure` coûtent 3,4 pts (v1.0) et 4,2 pts (Gemma) sur les lignes du modèle ; Gemma dit « checking gawk » ou « 6 sections lib lib » au lieu du résultat.
- **Garde-fous à poser avant l'activation** (causes des 6 régressions) :
  - se taire quand la dernière ligne n'est pas une ligne de répertoire de make : elle porte déjà le bilan (`built kvstored (69 objects)`, `v3-build-native-0013`) ;
  - se taire quand configure imprime un tableau de fin (`Media A4`, `v3-build-native-0064`) ;
  - ne jamais compter les avertissements : le compte des lignes `warning:` diffère du compte réel ; dire « avec avertissements, dont {fichier} ».
- **Gain estimé** : +1,2 à +2,0 pts avant garde-fous, +1,5 à +2,3 après si les 6 régressions tombent.

### L3. Faux rejets du garde-fou d'ancrage (post_process)

- **Fichiers** : `src/steph/grounding.py`, `src/steph/narrator.py` (`_llm_say` : repli si seule la reprise du statut survit), `tests/test_grounding.py`.
- **Règles** : jetons qui commencent par un chiffre lus en entier ; nombres composés en lettres FR et EN exclus des identifiants ; point suivi d'une espace et d'une capitale traité comme fin de phrase, même après un chiffre ; repli construit en code quand le flux ancré ne contient plus que le statut. Exemples dev : `v3-history-qa-0010`, `0041`, `0054`, `0056`, `v3-build-native-0031`.
- **Preuve** : l'ancrage coûte 2,0 pts à Gemma et 8,6 pts sur ses questions à réponse présente ; 28 réponses de Gemma perdent 2,4 pts par faux rejet, 6 en gagnent 0,4.
- **Risque relevé** : un identifiant numérique présent dans l'historique laisse passer une réponse hors sujet (`v3-history-qa-0100` chez v1.0 : « inet 127.0.0.1 » au lieu de « Pas dans l'historique »). Le garde-fou vérifie l'ancrage, pas la pertinence.
- **Gain estimé** : +1,0 pt pour Gemma, -0,2 pour v1.0.
- **Fait (branche `aids/L3`)**. Écart de modèle corrigé dans `score_production.py` : quand seule la reprise du statut survit, la production dit déjà le repli (`_drop_leading_status` vide le flux) ; seul le chemin des détails (`strip_status` faux) disait « Échec. » seul, corrigé par `_drop_lone_status`. Référence corrigée : Gemma 59,1 / 59,7 / 59,5, v1.0 inchangé.
- **Mesure dev, graines 7 / 42 / 123** : Gemma 59,1 / 59,7 / 59,5 -> 60,3 / 60,7 / 60,6 (**+1,1**) ; v1.0 52,7 / 52,0 / 51,3 -> 52,6 / 51,8 / 51,2 (**-0,1**). Réponses changées sur le fond : 16 par graine pour Gemma (11 ou 12 mieux, 1 moins bien), 3 à 5 pour v1.0 (0 mieux, 1 ou 2 moins bien) ; s'y ajoutent 30 à 70 réponses où seul le double point final « .. » disparaît.
- **Réponses devenues fausses** (relues à la main, 67 réponses de fond sur 6 runs) : `v3-history-qa-0100@en` chez v1.0 (3 graines, adresse de `lo0` donnée pour la carte Wi-Fi, limite connue) ; `v3-disk-memory-0032@fr` chez Gemma graine 7 (« Utilisation 44 % » pour un taux de mémoire libre ; la phrase n'était coupée que par accident, son premier mot en capitale pris pour un nom propre). Devenues justes : 5 à 7 « Pas dans l'historique » faux par graine chez Gemma.

### L4. Symboles retirés de la lecture telle quelle (code_answer)

- **Fichiers** : `src/steph/narrator.py` (branche lecture telle quelle), tests.
- **Règle** : retirer `***`, `**`, `==>`, `###`, `---` et les balises `[INFO]`, `[warn]` avant la synthèse. Source : messages de `make`, `nslookup`, `helm`, `prettier` en dev.
- **Preuve** : 12 évaluations changées ; 6 passaient à 0 par l'interdit global `\*\*`. Une personne aveugle entend sinon « astérisque astérisque astérisque ».
- **Gain estimé** : +0,6 pt.
- **Fait (branche `aids/L4`)** : `strip_symbol_runs` dans `src/steph/textproc.py`, appelée par la lecture telle quelle de `narrator._finish` et par `score_production.py`. Retire `**` et plus, `==>`, `###` isolés, les balises `[INFO]`, `[debug]`, et garde le mot des balises `[warn]`, `[ERROR]`. Un `---` ne part que s'il encadre la ligne (`--- x ping statistics ---`, `---- tests::x stdout ----`).
- **Pièges trouvés à la relecture** : `***` d'`apt-cache policy` marque la version installée (gardé quand un nombre suit) ; `----------` est un mode `ls -l` ; `--- fichier` est l'en-tête d'un diff ; `--- FAIL` porte le verdict de `go test` ; une ligne de colonnes soulignées reste entière. Chacun a un test.
- **Mesure dev, 3 graines** : v1.0 52,7/52,0/51,3 -> 53,3/52,6/51,9 ; Gemma 58,7/59,4/59,2 -> 59,3/60,0/59,8. 14 réponses changées par run (7 cas, 2 langues), 5 montent, 0 descend, 0 devenue fausse. Relecture ligne à ligne des 58 lignes distinctes que la fonction change sur toutes les sorties dev, pas seulement les lectures telles quelles.

### L5. Bloc de faits extraits en code (input_change, actif par défaut depuis 20cfa0d)

- **Fichiers** : `src/steph/prompts.py`, `src/steph/digest.py`, `src/steph/config.py` (réglage `facts_block`, vrai par défaut depuis `20cfa0d`, décision utilisateur du 2026-09-29), `bench/matrix/v3/tools/facts_harness.py` pour le harnais variante.
- **Contenu** : statut, compteurs (tests, erreurs, avertissements), erreur principale avec fichier et ligne, dernière ligne de bilan de l'outil, projet construit. Le digest qui garde les lignes d'erreur et de bilan n'a **pas de marge sur ce banc** : 2 faits manqués sur 509 chez v1.0 et 0 sur 434 chez Gemma sont coupés par `digest`.
- **Preuve** : 443 faits manqués sur 509 (v1.0) et 379 sur 434 (Gemma) sont dans l'entrée du modèle : le modèle voit le fait et ne le prend pas. Un bloc de faits en tête vise exactement ce défaut.
- **Mesure à faire** : Gemma brut et v1.0 sur l'A1000, harnais dev variante, 3 graines, `score_production.py`. Tout gain impose de réentraîner (G3 et v1.0).
- **Gain estimé** : non mesuré ; plage plausible 0 à +3 pts pour Gemma brut, inconnue pour v1.0 qui n'a jamais vu ce format.
- **Mesuré** (`docs/aids-input-l5.md`, A1000, dev, 3 graines) : Gemma brut **+1,5 pt** (IC [0,4 ; 2,7]), +7,1 sur les cas avec bloc ; v1.0 -0,6 (IC [-1,7 ; 0,5], non établi).
- **Actif en production** depuis `20cfa0d` : l'entrée réelle du modèle porte le bloc. Banc et corpus alignés le 2026-09-29, voir ci-dessous.

#### Banc v3 aligné sur L5

- `v3lib.rebuild_summary_input` et `generic_harness.summary_input` passent `facts=extract_facts(...)` quand `Config().facts_block` est vrai, comme `narrator._finish`.
- Entrées de résumé des cas régénérées par `build_inputs.py` (454 cas du banc sur 968 résumés reçoivent un bloc), harnais par `facts_harness.py` depuis `harness/pre-l5/`.
- Preuve : `bench/matrix/v3/tools/test_l5_production.py` compare chaque entrée de résumé dev à celle que `Narrator._finish` passe au modèle, profils affiné et générique ; `validate.py` : 1 083 cas et 1 105 cas des lots, 0 erreur.
- Anciens harnais gardés dans `bench/matrix/v3/harness/pre-l5/` : X3, D5 et tout chiffre antérieur se rejouent dessus. Empreintes : `bench/matrix/v3/README.md`, section « Harnais et empreintes ».

#### Pour que L5 entre dans le prochain affinage

- `label.build_messages` (étiquetage, `compose_k3`, `rebuild_p15`, `build_dataset_release`) et `build_feature_corpus.summary_entry` ajoutent le bloc tiré de la sortie brute. `tests/test_l5_corpus_alignment.py` compare leur entrée à celle de `Narrator` sur des enregistrements synthétiques.
- Appariement étiquette-brut (`header_key` de `compose_k3`, `rebuild_p15`, `build_dataset_release`) : le bloc est ignoré, un corpus étiqueté avant L5 et un corpus régénéré retrouvent le même brut.
- `data/final-x4-l5` : `bench/matrix/finetune/x4_l5_inputs.py` réécrit les résumés de `data/final-x4` avec le bloc, sur la machine du corpus ; étiquettes, prompts système et autres fichiers (détail, progression, flux) inchangés. Les étiquettes 27B restent valides : seule l'entrée change.
- G3 et R3-T4 (`g3_pairs.generic_messages`, `onpolicy_sample.production_messages`) relisent le bloc dans la ligne : la sortie d'une ligne de corpus est déjà réduite, le bloc ne s'y recalcule pas. La sélection DPO de G3b doit donc lire `data/final-x4-l5`, pas `data/final-x4`.
- Les chaînes `compose_k3.py` (`--fr-raw`, `--en-raw`, `--feature-raw`) reconstruisent les résumés depuis le brut : elles donnent le bloc sur `final-x4` comme sur `final-x4-l5`.
- Régénéré le 2026-09-29 sur l'hôte de la 3060 (CPU, `nice -n 19`), `/mnt/backup-hdd/stephbench-tmp/ft/data/final-x4-l5` : 5 034 lignes comme `final-x4`, étiquettes, prompts système et champs identiques ligne à ligne, `SHA256SUMS` vérifié.

| Fichier | Lignes | Avec bloc | Sans fait extrait | Sans brut apparié |
|---|---:|---:|---:|---:|
| `linux-dev` | 739 | 78 | 658 | 3 |
| `linux-low` | 680 | 118 | 559 | 3 |
| `macos` | 330 | 26 | 303 | 1 |
| `snapshot-linux-dev` | 941 | 292 | 649 | 0 |
| `snapshot-linux-low` | 848 | 304 | 543 | 1 |
| `linux-low.en` | 270 | 74 | 196 | 0 |
| `macos.en` | 289 | 62 | 227 | 0 |
| `detail`, `progress`, `flux` | 937 | copiés | - | - |

- Sur 4 089 résumés appariés, 398 ont une sortie étiquetée différente du digest actuel de leur brut (digest changé depuis l'étiquetage, ou appariement par mots partagés) : le bloc vient du brut apparié, la sortie reste celle que l'étiquette a lue.
- Les 8 lignes sans brut apparié gardent leur entrée sans bloc. `serveur Xeon` n'a pas de corpus brut sous `/root/steph-ft/data` : la régénération n'y est pas possible sans copie de corpus.

### L6. Coupe à `max_words` (post_process)

- **Fichiers** : `src/steph/narrator.py` ou `src/steph/textproc.py`.
- **Preuve** : 37 réponses trop longues (v1.0) et 23 (Gemma) ; plafond théorique 0,4 pt ; coupe naïve à 20 mots : 0,0 et +0,2.
- **Gain estimé** : négligeable. À faire seulement pour l'écoute, pas pour la note.

### Leviers testés et écartés

| Levier | Type | v1.0 | Gemma | Raison |
|---|---|---:|---:|---|
| Erreurs système courtes (`No such file`, `Operation not permitted`) redites dans la langue de la session, `resolve()` avant la lecture telle quelle | code_answer | -0,3 | -0,3 | sujet mal extrait (« accéder à », « usb »), perte du nom et du délai curl |
| Question « quelle erreur a donné X » répondue par `resolve()` sur la commande de l'historique | qa_code | -0,1 | -0,1 | 2 questions touchées, la mauvaise commande choisie une fois |
| Réponse recopiée remplacée par le repli construit en code | post_process | -0,4 | -1,5 | le repli recopie aussi une ligne, et moins bien |
| Détection en code d'une réponse absente de l'historique | qa_code | - | - | aucun signal exact trouvé ; l'ancrage dit déjà « Pas dans l'historique » (absentes : v1.0 64 contre 55 sans ancrage, Gemma 82 contre 73) |

## 4. Tous les leviers ensemble sur master

L1 à L4 actifs par défaut (réponses en code, post-traitement) ; L5 fusionné derrière `facts_block`, désactivé au moment de cette mesure, donc sans effet sur ces chiffres. Il est actif en production depuis `20cfa0d` : ces chiffres restent ceux des harnais d'avant L5 (`harness/pre-l5/`).
Mesure hors ligne sur les sorties existantes (`v3-rescore/runs`), `score_production.py`, 3 graines. « Avant » : `score_production.py` de master avant fusion (`d3aaee9`), avec la correction de modélisation du statut seul apportée par L3 (sans elle, Gemma avant vaut 0,3 à 0,5 de moins). Écart apparié par cas, bootstrap de `power_v3` (10 000 tirages). Harnais inchangés : dev `1b8f7402`, test `a463f8bf`, générique dev `247b1141`, test `e4abce1c`.

| Split | Modèle | Avant (g. 7 / 42 / 123) | Après (g. 7 / 42 / 123) | Moyenne avant -> après | Écart apparié, IC 95 % |
|---|---|---|---|---:|---|
| dev | v1.0 | 52,7 / 52,0 / 51,3 | 59,5 / 58,9 / 58,2 | 52,0 -> **58,9** | **+6,9** [4,7 ; 9,2] |
| dev | Gemma 4 E2B brut | 59,1 / 59,7 / 59,5 | 67,7 / 67,9 / 68,0 | 59,5 -> **67,9** | **+8,4** [6,0 ; 11,0] |
| **test** | v1.0 | 53,3 / 53,2 / 53,0 | 58,7 / 58,3 / 58,2 | 53,2 -> **58,4** | **+5,2** [3,7 ; 6,9] |
| **test** | Gemma 4 E2B brut | 61,2 / 61,4 / 61,2 | 67,2 / 67,7 / 67,5 | 61,3 -> **67,5** | **+6,2** [4,6 ; 8,0] |

| Indicateur | dev | test |
|---|---:|---:|
| Part dite en code | 37,3 -> 40,8 % | 36,9 -> 40,5 % |
| Note des lignes dites en code | 64,0 -> 78,0 | 66,8 -> 78,6 |
| Note des lignes du modèle, v1.0 | 44,9 -> 45,7 | 45,2 -> 44,6 |
| Note des lignes du modèle, Gemma | 56,8 -> 60,9 | 58,0 -> 59,9 |
| Évaluations changées, v1.0 (3 graines) | 493 : 209 mieux, 8 moins bien | 647 : 254 mieux, 10 moins bien |
| Évaluations changées, Gemma (3 graines) | 401 : 250 mieux, 8 moins bien | 561 : 298 mieux, 12 moins bien |

- **Le test confirme** : gain plus faible que sur dev (v1.0 +5,2 contre +6,9 ; Gemma +6,2 contre +8,4), comme attendu pour des règles écrites en lisant dev ; les deux IC excluent 0, test de signe p < 0,0001.
- Les évaluations changées comptent aussi les « .. » finaux retirés par L3 : sans effet sur la note.
- Relecture dev, 40 réponses changées tirées au hasard (graine 20260929) parmi 118 changements de fond distincts : **1 devenue fausse**, `v3-history-qa-0100@en` chez v1.0 (adresse de `lo0` donnée pour la carte Wi-Fi ; limite connue de L3 : le garde-fou vérifie l'ancrage, pas la pertinence). 1 imprécise : `v3-vcs-git-0031@en` chez v1.0, deux branches collées sans séparateur, vraie mais mal lisible. 30 phrases dites en code, toutes exactes ; 10 phrases du modèle, dont 8 vraies.
- Défaut trouvé à la fusion et corrigé : L2 et L5 définissaient chacun `_CONFIGURE_ERROR` et `_CC_WARNING` au niveau du module de `digest.py` ; la seconde définition écrasait la première et L2 se taisait sur un `configure: error:` en fin de ligne `checking`. Les regex de L5 sont renommées `_FACT_*` ; le test de L2 rouge est redevenu vert.
- `generic_harness.py` recopie désormais `reaches_model` du harnais figé : `resolve()` dit plus de cas depuis L2, et le recalculer changeait l'empreinte du harnais générique.
- Fichiers : `bench/matrix/results/aids-integration/` (écarts appariés `pair-*.json`, scripts `dump_prod.py`, `pair.py`, `sample.py`).

## 5. Limites

| Limite | Effet |
|---|---|
| Gains mesurés sur le split où les règles ont été écrites | optimistes ; le test tranchera, une fois |
| Faits du banc écrits contre l'entrée tronquée du modèle | des phrases de code vraies sont notées 0 (6 évaluations relevées) ; la note composite sous-estime le code |
| `score_production.py` ne rejoue ni les règles par commande ni la durée en suffixe | écart possible avec ce qui est entendu sur une commande longue |
| Taxonomie par règles (seuil de recopie 50 %, classifieur de trigrammes) | la frontière recopie et mauvaise langue est floue |
| Une graine pour la taxonomie, trois pour les gains | la taxonomie porte le bruit d'une graine |
| Mesure hors ligne sur des sorties déjà produites | aucune phrase n'a été entendue en synthèse vocale dans steph ; L5 n'a d'effet qu'après un affinage avec le bloc |
