# G3c : TEST caché, une passe, contre G3b

Date : 2026-10-01, de 19:22 à 22:20. Rien sur le Mac : relais de fichiers par flux ssh seulement.

## Décision

**G3b off-ple3 reste le modèle livré. G3c n'est pas adopté** : la règle T5 contre G3b n'est pas tenue.

| Règle T5 (pré-enregistrée, `0d3b149`) | G3c - G3b off-ple3 (IC 95 %) | Verdict |
|---|---|---|
| Qualité non inférieure | +0,48 [-0,76 ; +1,67] | tenu |
| Meilleur sur au moins un axe | aucun IC au-dessus de 0 sur les axes pré-enregistrés : inventions A7 **-2,10 [-4,28 ; +0,04]** (p 0,049), formulation +2,5 [-6,7 ; +12,1], note de production +0,38 [-0,43 ; +1,17] | **non tenu** |
| Aucune régression significative | aucun IC défavorable qui exclut 0 | tenu |

- **Le seul gain significatif est hors règle** : qualité sur les réponses `reaches_model`, +2,06 [+0,48 ; +3,61]. C'est un sous-score de la qualité, absent des axes pré-enregistrés. Il n'est pas compté.
- **Inventions : tendance favorable, non établie.** La borne haute est à +0,04. Le DEV montrait déjà un bruit de graine du même ordre (t9s7 contre t9s42 : -2,60).
- **Contre-jugement 27B non lancé.** La condition pré-enregistrée était « le seul gain tient au 9B ». Aucun gain n'est significatif au 9B, donc elle n'est pas remplie.

## Modèles (une session, 3080 CUDA)

| Modèle | GGUF (sha256) | Harnais |
|---|---|---|
| **G3c** : t9s7 off-ple3, choisi au DEV avant le TEST | `3e36aeed1503032fbd831b40a70359d9770c4dd87543a7c71d9c0df7f7c7f76b`, 2,43 Go | générique `8d90a662` |
| G3b off-ple3 (G4b) | `eb6e76076b819d9e7a1bbb01e38e8cbf256eb3bd741b6cb0c6311a4a7ed3b429`, 2,43 Go | générique `8d90a662` |
| Gemma 4 E2B brut QAT q4_0 | `fa401b55b07ee70a54c6dae3903c783a6e65064312529ea57175cb5f8dec6634` | générique `8d90a662` |
| steph-speak v1.0 | `45414bd2af2daf5f…` | affiné `705fdcb9` |

## Tableau (banc v3 test aligné L5, 654 cas, 3 graines)

| Axe | G3c | G3b off-ple3 | Brut | v1.0 |
|---|---|---|---|---|
| Qualité `score_v3` | **64,1** | 63,7 | 60,6 | 50,6 |
| Qualité par graine 7 / 42 / 123 | 63,8 / 64,5 / 64,1 | 63,0 / 63,9 / 64,1 | 59,9 / 61,2 / 60,6 | 50,6 / 50,5 / 50,8 |
| Note de production (`score_production.py` au commit `42a5e9c`, aides D5 et D6) | **72,7** | 72,3 | 71,6 | 65,5 |
| Replis du garde-fou, par graine | 15 / 10 / 9 | 16 / 18 / 14 | 21 / 22 / 27 | 10 / 9 / 10 |
| `reaches_model` | **64,0** | 61,9 | 59,1 | 47,4 |
| Résumés | 61,2 | 60,7 | 57,6 | 51,1 |
| Questions | 88,3 | 88,6 | 85,7 | 46,9 |
| Questions, réponse présente / absente | 89,0 / 86,7 | 90,0 / 85,0 | 86,7 / 83,3 | 47,0 / 46,7 |
| Abstentions, réponse présente (par graine) | 1-2-2 | 1-2-2 | 1-1-2 | 8-9-9 |
| Abstentions, réponse absente (par graine) | 33-34-33 | 29-34-35 | 20-29-30 | 19-19-18 |
| FR / EN | 64,9 / 63,4 | 63,9 / 63,4 | 60,8 / 60,4 | 49,8 / 51,5 |
| Inventions A7 9B (2 478 verdicts) | **15,2 %** | 17,3 % | 17,4 % | 29,2 % |
| Douteux A7 | 6,9 % | 7,0 % | 7,6 % | 9,1 % |
| Mauvaise langue, prompt FR / EN | 5,57 / **2,18 %** | 5,00 / 2,58 % | 6,30 / 2,74 % | 8,96 / 12,27 % |
| Sortie FR sous prompt EN (98 évaluations) | **6,8 %** | 8,8 % | 10,5 % | 39,5 % |

## Écarts appariés

Bootstrap apparié par cas, 10 000 tirages, graine 20260928 (`g3b_eval.py` via `eval/g3c_eval.py`). Chiffres dans `eval/g3c-eval.json`.

| Axe | G3c - G3b | G3c - brut | G3c - v1.0 | G3b - brut |
|---|---|---|---|---|
| Qualité | +0,48 [-0,76 ; +1,67] | **+3,56 [+1,89 ; +5,21]** | **+13,48** | **+3,08 [+1,66 ; +4,49]** |
| Note de production | +0,38 [-0,43 ; +1,17] | **+1,10 [+0,11 ; +2,11]** | **+7,19** | +0,72 [-0,21 ; +1,66] |
| `reaches_model` | **+2,06 [+0,48 ; +3,61]** | **+4,87** | **+16,55** | **+2,82** |
| Résumés | +0,56 [-0,78 ; +1,88] | **+3,67** | **+10,13** | **+3,11** |
| Questions | -0,24 [-2,62 ; +2,38] | +2,62 [-0,24 ; +6,19] | **+41,43** | **+2,86** |
| Questions, réponse présente | -1,00 [-3,83 ; +1,83] | +2,33 | **+42,00** | +3,33 |
| Questions, réponse absente | +1,67 [-2,50 ; +7,50] | +3,33 | **+40,00** | +1,67 |
| FR | +0,97 [-0,55 ; +2,57] | **+4,11** | **+15,02** | **+3,14** |
| EN | -0,02 [-1,71 ; +1,67] | **+3,01** | **+11,94** | **+3,03** |
| Inventions A7, 3 graines | -2,10 [-4,28 ; +0,04] | -2,14 [-4,76 ; +0,52] | **-14,00** | -0,04 [-2,70 ; +2,62] |
| Mauvaise langue, prompt FR | +0,56 [-1,21 ; +2,34] | -0,73 | **-3,39** | -1,29 |
| Mauvaise langue, prompt EN | -0,40 [-1,53 ; +0,65] | -0,56 | **-10,09** | -0,16 |
| Sortie FR sous prompt EN | -2,04 [-6,12 ; +2,04] | -3,74 [-8,84 ; +1,36] | **-32,65** | -1,70 |
| Formulation, net | +2,5 [-6,7 ; +12,1] | - | - | - |

### Formulation à l'oral (G3c contre G3b, juge 27B)

| | G3c | G3b | Égalités | Net G3c (IC 95 %) |
|---|---|---|---|---|
| Toutes (240 paires) | 68 | 62 | 110 (dont 80 instables) | +2,5 [-6,7 ; +12,1] |
| Prompt FR (117) | 36 | 31 | 50 | +4,3 [-9,4 ; +17,9] |
| Prompt EN (123) | 32 | 31 | 60 | +0,8 [-11,4 ; +13,8] |

Paires tirées par hachage parmi 916 réponses qui diffèrent (graine 7) ; 0 erreur de juge.

## Contrôles

| Contrôle | Résultat |
|---|---|
| Reproductibilité des références | **9 runs sur 9 identiques**, 1 308 réponses sur 1 308 chacun : G3b off-ple3 contre les runs de G4b, brut et v1.0 contre les runs de G3b |
| Juge A7, contrôles avant / après | 6/6 FR et EN, passes A et B, avant et après |
| Juge A7, erreurs | une évaluation du brut en erreur à la graine 7 après 3 essais, exclue ; 0 ailleurs |
| Juge de formulation, contrôles plantés X5 | **77/80 avant et après** (57/60 plantés, 20/20 identiques) ; biais de position 48,7 % sur les contrôles |
| GGUF | sha256 vérifiés par le script avant le premier run |

## Protocole

| Élément | Valeur |
|---|---|
| Générations | 3080 CUDA, llama.cpp `9588757` (celui de G3b et G4b) ; `bench_run.py` au commit `42a5e9c` ; échantillonnage de production, `--cache-ram 0`, `-ngl 99` ; 2 couloirs, 12 runs, 0 réponse manquante ; `eval/eval-3080.sh` |
| Juge A7 | Qwen3.5 9B Q4_K_M `03b74727`, `judge_x3.py` de G3, 2 passes, cache neuf ; les 12 runs sur la même carte ; jusqu'à 3 essais par run en erreur |
| Juge de formulation | Qwen3.5 27B Q4_K_M `84b5f7f1`, serveur Xeon en CPU, cœurs 0-31, 48 Go, nice 19, un slot, `--cache-ram 0`, un seul 27B à la fois ; `eval/style-xeon.sh` |
| Relais | `eval/relay.sh` : runs graine 7 de la 3080 vers serveur Xeon, sha256 identique aux deux bouts |
| Statistiques | `eval/g3c_eval.py` (enveloppe de `gemma/g3b/g3b_eval.py`, plus le contrôle de reproductibilité) sur la 3080 |
| Hors dépôt | 3080 `/root/steph-ft/g3c/eval/` (runs, verdicts, journaux) ; serveur Xeon `/root/steph-ft/g3c/style/` |

## Écarts et incidents

| Écart | Effet |
|---|---|
| Archive du dépôt sans les modules de premier niveau de `bench/matrix` (`score.py`, `facts.json`) | le premier passage de formulation a échoué à l'import, avant toute paire ; complétée et relancée à 20:43 ; un second lancement accidentel a été arrêté par ses PID exacts avant tout jugement |
| Premier transfert du GGUF brut coupé à 3,0 Go | fichier tronqué supprimé et recopié avec contrôle de taille ; sha256 `fa401b55…` vérifié |
| Formulation en attente du 27B de G5c (un seul 27B sur serveur Xeon) | début à 20:43 au lieu de 19:33 |
| Copies Q4_0 `g3c-s42` et `g3c-t9s42` effacées de `/dev/shm/g3c/` sur la 3080 pour faire de la place | doublons volatils posés par G3c ; les originaux sont sur serveur Xeon avec sha256 vérifiés |
| Note de production au commit courant (D6 actif) | 72,3 pour G3b contre 68,8 publié en G3b : barème différent ; seuls les écarts de cette session se comparent |
| Une seule graine d'entraînement au TEST (t9s7) | le DEV a montré un bruit de graine du même ordre que l'effet cherché |

## Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| G3c non inférieur à G3b en qualité | VÉRIFIÉ | `eval/g3c-eval.json`, +0,48 [-0,76 ; +1,67], 3 graines ; échouerait si l'IC passait sous 0 | une graine d'entraînement |
| Aucun axe pré-enregistré meilleur, donc T5 non tenue | VÉRIFIÉ | IC des inventions, de la formulation et de la note de production couvrant 0 | inventions à +0,04 de la significativité ; 27B non lancé |
| Aucune régression contre G3b | VÉRIFIÉ | tous les IC défavorables couvrent 0 | puissance limitée : un point d'inventions n'est pas exclu |
| Banc reproductible | VÉRIFIÉ | 9 runs de référence identiques à 100 % ; échouerait à la première réponse différente | - |
| Juges stables pendant la session | VÉRIFIÉ | A7 6/6 avant et après ; formulation 77/80 avant et après | aucune vérité humaine |
| Formulation à l'écoute | JAMAIS EXÉCUTÉ | - | personne n'a écouté une réponse de G3c |
