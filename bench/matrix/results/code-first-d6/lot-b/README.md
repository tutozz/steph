# D6 lot B : scripts et fichiers dits en code

Branche `d6/B`. Code dans `src/steph/digest.py` (bloc « D6 lot B »), chaînes `resolve.d6b.*` dans `strings.py`, tests `tests/test_digest_d6_b.py`.
Entrée du modèle inchangée : harnais générique dev régénéré, empreinte `e96d54d4` identique.

## Règles

| Fonction | Sortie reconnue | Phrase |
|---|---|---|
| `_script_error` | script en échec : `script: line N: msg` de bash, `outil: msg` des outils GNU ; outil GNU lancé seul en échec | dernière erreur, compte si plusieurs, fichiers nommés quand un même outil échoue sur 3 fichiers au plus, dernier message chiffré du script |
| `_script_error` (code 0) | script qui rend 0 après **une seule** erreur | « Terminé, mais une erreur : … » ; plusieurs erreurs sous un code 0 : abstention |
| `_verbose_count` | `rm -v`, `mkdir -v`, `split --verbose`, `chmod -v/-c`, `chown -v/-c`, `chgrp -v`, `cp -v`, `mv -v`, `ln -v`, `shred -v`, `tar -cv/-xv` (GNU et bsdtar) | compte, dossier commun, mode ou propriétaire unique |
| `_checksum` | `md5sum -c`, `sha*sum -c`, `b2sum -c`, `shasum -c` | comptes des avertissements de l'outil, premiers noms, fichiers conformes sans tube |
| `_grep_count` | `grep -r`, `-l`, `-c` ou plusieurs chemins, sans tube | lignes, fichiers, fichier le plus touché ; motif lu seulement s'il est un mot simple |
| `_diff_brief` | `diff -q`, `diff -rq` | fichiers qui diffèrent, éléments d'un seul côté |
| `_wc_total` | `wc -l/-w/-c/-m` sur plusieurs fichiers | total contrôlé par la somme, plus gros fichier |
| `_rsync_summary` | `total size is`, `--stats` (GNU), `Transfer starting` (openrsync) | taille totale, fichiers transférés ; `-h` et `--dry-run` : abstention |

Provenance : sorties réelles capturées en `LANG=C` et `LANG=fr_FR.UTF-8` sur une machine du labo (`gen.sh`, `real-en.txt`, `real-fr.txt` : coreutils 9.x, bash 5.2, GNU tar 1.35, rsync 3.4.1), catalogues `fr.mo` de ces outils, sorties et cas du split **dev**. Aucun cas du split test lu, aucune réponse de modèle lue.

Pièges D6 traités, chacun avec un test :

- espaces insécables des traductions (`Attention\xa0:`, `shred: f\xa0: étape`) ;
- dernière ligne générique de tar : cause gardée, « erreur non récupérable » ajoutée seulement si l'erreur dite vient de tar ;
- plusieurs échecs du même outil : compte et noms ;
- messages coupés aux mots, élisions françaises gardées (`_quote_free`, `_clean` les cassait) ;
- message français dans une session anglaise : abstention ;
- accords (`1 élément`, `2 éléments`).

## Mesure hors ligne, dev, 3 graines (`measure.py`)

| Modèle | Avant (g. 7 / 42 / 123) | Après | Moyenne |
|---|---|---|---|
| v1.0 (harnais affiné L5) | 58,5 / 58,1 / 57,7 | 63,8 / 63,4 / 62,9 | 58,1 -> **63,4** (+5,2) |
| Gemma 4 E2B brut L5 (substitut de G3b) | 68,9 / 68,8 / 68,9 | 73,2 / 73,1 / 73,0 | 68,9 -> **73,1** (+4,2) |
| G3b | non mesuré : passe dev de la 3080 toujours en attente | | |

| Indicateur | Valeur |
|---|---|
| Part dite en code | 40,8 -> **49,8 %** (+77 évaluations sur 858) |
| Évaluations changées | 77 par graine ; 3 graines : v1.0 195 mieux, 8 moins bien ; Gemma 176 mieux, 3 moins bien |
| Lignes déjà dites en code et changées | 0 |
| Mode hybride estimé (phrase de code puis réponse du modèle) | moins bon que le code seul sur chaque règle (scripts : v1.0 +2,05 contre +2,73, Gemma +1,71 contre +1,91) : aucun réglage hybride pour ce lot |

Relecture à la main : les 77 phrases (39 cas, FR et EN, `changed-dev.txt`) confrontées à la sortie brute. **Aucune fausse.** Corpus publics (`bench/fixtures.json`, `extra_fixtures.json`, Steph Speak Bench v1) : 14 phrases nouvelles, toutes relues et vraies.

Baisses expliquées :

| Cas | Cause |
|---|---|
| `v3-files-0106` (v1.0, 0 point) | phrase vraie ; interdit du banc écrit contre l'entrée tronquée (`mesure_017` est bien en échec dans la sortie brute) |
| `v3-files-0069` (note 0 inchangée) | phrase vraie ; même défaut du banc (« le fichier existe » est dans la sortie brute) |
| `v3-shell-scripts-0024@fr` (Gemma -0,10) | phrase juste mais longue : pénalité de longueur |

## Limites

| Limite | Effet |
|---|---|
| Règles écrites en lisant dev, gain dans l'échantillon | le test, lu une fois à l'intégration, donnera moins (D5 : environ 25 % de moins) |
| Poids du banc : scripts 81 cas pour une cible de 15 | `_script_error` pèse plus dans la note que dans l'usage |
| G3b absent du dev | gains Gemma majorés d'au plus la marge G3b-brut (1,2 pt au test) |
| « Dernier message » cite une ligne du script telle quelle | une ligne anglaise peut être lue dans une phrase française (l'inverse est exclu) |
| Jamais entendu en synthèse vocale | chemins, deux-points successifs (« Dernier message : Bilan : … ») non écoutés |
