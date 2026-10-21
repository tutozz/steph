# G3, évaluation : Gemma 4 E2B affiné contre le brut, au banc v3 test

Date : 2026-09-29. Split TEST (654 cas, 1 308 évaluations FR + EN), 3 graines de banc (7, 42, 123), une seule session sur la 3080. Rien sur le Mac.

## Décision

**Le brut reste** (règle T5 stricte). Modèle retenu : **Gemma 4 E2B QAT q4_0 officiel**, `gemma-4-E2B_q4_0-it.gguf`, sha256 `fa401b55b07ee70a54c6dae3903c783a6e65064312529ea57175cb5f8dec6634` (serveur Xeon `/root/steph-ft/gemma/`, A1000 `/root/steph-ft/loop/x3/raw/`).

| Règle T5 | SFT 42 contre brut | DPO 42 contre brut |
|---|---|---|
| Qualité non inférieure | **+2,94 [+1,58 ; +4,29]**, meilleur | **+2,97 [+1,57 ; +4,37]**, meilleur |
| Meilleur sur au moins un axe | inventions, formulation, questions : **oui** | inventions, formulation, questions : **oui** |
| Aucune régression significative | **mauvaise langue sous prompt EN +2,18 [+0,40 ; +4,04]** | **mauvaise langue sous prompt EN +3,31 [+1,37 ; +5,41]** |
| Verdict | **non tenu** | **non tenu** |

**Décision contestable.** Le SFT 42 gagne sur quatre axes et ne perd que sur un seul, de 2,2 pts : 5,8 % de réponses dans la mauvaise langue sous prompt anglais, contre 3,6 % pour le brut. Je garde la lecture stricte, comme en R2. Si l'utilisateur accepte cette régression, le candidat est **SFT 42** (`sft-s42-Q4_0.gguf`, sha256 `93eb13e9040bcd9e4d66db5499d875678741593560d19653fc4f707bb5e10b2f`), pas le DPO.

- Le DPO n'apporte rien de significatif sur le SFT et ajoute sa propre régression de langue : +1,13 [+0,16 ; +2,18].
- **Cause de la régression, lue sur les sorties** : sous prompt anglais, quand la commande affiche une sortie en français (locale FR), l'affiné répond plus souvent en français. Cas signalés au classifieur : brut 45, SFT 72, DPO 86 sur 1 239.
- **Correctif proposé (G3-b)** : ajouter au mix des exemples EN dont la sortie de commande est en français, puis refaire le SFT sur une graine et repasser ce banc. Les autres axes laissent une marge large.

## Tableau (split test, 3 graines)

Inventions : juge A7 sur les réponses `reaches_model`, 3 graines pour les 5 modèles (826 réponses par graine). Mauvaise langue : méthode de R2 (`r2_lang.py`, mots-outils), sur les évaluations `reaches_model`.

| Modèle | GGUF | Qualité | reaches_model | Résumés | Questions | FR / EN | Inventions | Douteux | Mauvaise langue FR / EN |
|---|---|---|---|---|---|---|---|---|---|
| Gemma 4 E2B brut QAT q4_0 | 3,35 Go | 60,5 | 58,6 | 57,5 | 85,7 | 60,2 / 60,7 | 19,7 % | 9,6 % | 5,6 / **3,6** % |
| **SFT 42** | 3,35 Go | **63,4** | **61,4** | **60,4** | 89,1 | 62,6 / 64,3 | 17,0 % | 6,7 % | 5,5 / 5,8 % |
| DPO 42 (sur SFT 42) | 3,35 Go | **63,5** | 60,4 | 60,3 | **89,9** | 62,4 / 64,6 | 16,2 % | 6,7 % | 5,8 / 6,9 % |
| Granite 4.1 3B affiné (R3-T3) | 2,10 Go | 61,5 | 58,3 | 59,4 | 79,2 | 60,4 / 62,7 | **14,4 %** | 5,9 % | **4,8** / 9,2 % |
| steph-speak v1.0 (R1) | 0,22 Go | 50,0 | 45,7 | 50,4 | 46,9 | 48,9 / 51,0 | 31,4 % | 9,7 % | 7,9 / 12,6 % |

- Qualité par graine : brut 59,9 / 60,9 / 60,7 ; SFT 63,2 / 63,9 / 63,2 ; DPO 63,4 / 63,4 / 63,7.
- **v1.0 reproduit R2 à l'identique** : qualité 49,96, mauvaise langue 7,91 / 12,59 %, inventions graine 7 à 31,2 %. Même GGUF, même harnais, même carte : le banc est déterministe.

## Écarts appariés

Bootstrap apparié par cas, 10 000 tirages (`power_v3`). Inventions en points de % des réponses.

| Axe | SFT 42 - brut | DPO 42 - brut | DPO 42 - SFT 42 |
|---|---|---|---|
| Qualité | **+2,94 [+1,58 ; +4,29]** | **+2,97 [+1,57 ; +4,37]** | +0,03 [-0,73 ; +0,79] |
| reaches_model | **+2,83 [+1,10 ; +4,59]** | **+1,88 [+0,06 ; +3,76]** | -0,95 [-2,04 ; +0,05] |
| Résumés (584 cas) | **+2,89 [+1,41 ; +4,37]** | **+2,83 [+1,25 ; +4,38]** | -0,06 [-0,93 ; +0,77] |
| Questions (70 cas) | **+3,33 [+0,95 ; +6,43]** | **+4,17 [+1,55 ; +7,62]** | +0,83 [-0,12 ; +2,14] |
| Questions, réponse présente (50) | **+3,33 [+0,67 ; +7,00]** | **+4,50 [+1,50 ; +8,83]** | +1,17 [-0,17 ; +2,83] |
| Questions, réponse absente (20) | +3,33 [0,00 ; +9,17] | +3,33 [0,00 ; +9,17] | 0 |
| FR / EN | **+2,34** / **+3,54** | **+2,10** / **+3,85** | -0,25 / +0,31 |
| Inventions, 3 graines | **-2,74 [-5,41 ; -0,12]** | **-3,51 [-6,30 ; -0,73]** | -0,77 [-2,10 ; +0,52] |
| Formulation à l'oral, net, 240 paires | **+29,6 [+20,8 ; +37,9]** | **+35,8 [+27,9 ; +43,8]** | +4,2 [-3,8 ; +12,1] |
| Mauvaise langue, prompt FR (413) | -0,08 [-2,18 ; +1,94] | +0,24 [-2,10 ; +2,50] | +0,32 [-0,81 ; +1,53] |
| **Mauvaise langue, prompt EN (413)** | **+2,18 [+0,40 ; +4,04]** | **+3,31 [+1,37 ; +5,41]** | **+1,13 [+0,16 ; +2,18]** |

Contre les autres modèles :

| Comparaison | Qualité | Questions | Inventions | Mauvaise langue EN |
|---|---|---|---|---|
| SFT 42 - Granite 4.1 3B | +1,93 [-0,36 ; +4,20] | **+9,88 [+3,21 ; +17,26]** | +2,62 [-0,48 ; +5,73] | **-3,39 [-6,13 ; -0,65]** |
| SFT 42 - v1.0 | **+13,48 [+10,88 ; +16,14]** | **+42,14** | **-14,41** | **-6,78** |
| brut - v1.0 | **+10,54 [+7,79 ; +13,34]** | **+38,81** | **-11,66** | **-8,96** |
| Granite 4.1 3B - v1.0 | **+11,55 [+8,94 ; +14,10]** | **+32,26** | **-17,03** | **-3,39** |

- **Piège R2 absent** : abstentions sur réponse présente (150 réponses par graine) brut 1 / 1 / 2, SFT 1 / 2 / 2, DPO 1 / 2 / 2. Sur réponse absente (60), l'affiné s'abstient plus, à raison : brut 20 / 29 / 30, SFT 33 / 35 / 35, DPO 31 / 34 / 34.
- **Granite 4.1 3B** : qualité égale au SFT 42, inventions égales, 1,25 Go de moins. Questions nettement moins bonnes (-9,9), mauvaise langue EN pire (9,2 %). À garder en concurrent pour G4 et G5.

## Formulation à l'oral

Juge 27B (`judge_style_v3.py`, verdict global seul), graine 7, 240 paires différentes tirées par hachage (`style_sample.py` de R2). Les deux ordres ; un verdict instable devient une égalité.

| Paire | Affiné préféré | Brut préféré | Égalités (instables) | Net, IC 95 % | FR | EN |
|---|---|---|---|---|---|---|
| SFT 42 contre brut | 102 | 31 | 107 (78) | **+29,6 [+20,8 ; +37,9]** | +30,8 (104) | +28,7 (136) |
| DPO 42 contre brut | 106 | 20 | 114 (95) | **+35,8 [+27,9 ; +43,8]** | +34,6 (107) | +36,8 (133) |
| DPO 42 contre SFT 42 | 51 | 41 | 148 (86) | +4,2 [-3,8 ; +12,1] | +4,2 (119) | +4,1 (121) |

**Revalidation du juge** sur la configuration de cette session (3080, 32 couches sur GPU, `--parallel 2`) : 57 contrôles plantés sur 60 (95,0 %), 20 égalités sur 20, biais de position 48,7 %. X5 donnait 96,7 % et 49,6 % sur l'hôte CPU.

## Protocole

| Élément | Valeur |
|---|---|
| Banc | v3 au HEAD `dac21af` ; `harness/test.json` identique à `a52223c` (md5 `9bb44843…`) ; `test.generic.json` régénéré par `generic_harness.py`, md5 `1ea3b078…`, identique à X3 |
| Harnais par modèle | Gemma brut, SFT, DPO : profil générique (entraînés avec `--generic-prompt`) ; v1.0 et Granite 4.1 3B : profil affiné (`test.json`), comme X3 et R3-T3 |
| Génération | 3080 CUDA, llama.cpp `9588757`, `bench_run.py` au HEAD (échantillonnage de production, `--cache-ram 0`), `-ngl 99`, 3 couloirs sur une file partagée, 15 runs, 0 réponse manquante |
| Juge A7 | Qwen3.5 9B Q4_K_M `03b74727…` sur la 3060, `judge_lib` A7 intact, 2 passes, cache par (harnais, cas, réponse), verdicts R2 de v1.0 en cache. Contrôles 6/6 FR et 6/6 EN, passes A et B, avant et après chacune des 3 passes |
| Juge de formulation | Qwen3.5 27B Q4_K_M `84b5f7f1…` sur la 3080, 32 couches sur GPU, reste en RAM ; environ 9 s par paire, deux ordres compris |
| Statistiques | `g3/g3_eval.py` : `power_v3.compare` (unité le cas, moyenne des graines puis des langues) ; mauvaise langue par évaluation comme `r2_lang.py` ; formulation par bootstrap sur les paires |
| Fichiers | `g3/eval/g3-eval.json` (chiffres seuls), scripts `g3/eval/*.sh`, journaux des juges `g3/eval/*-run.done.txt` ; sorties brutes et verdicts hors dépôt (split test caché) : 3080 `/root/steph-ft/g3/eval/`, 3060 `…/gemma/g3/judge-test/` |

## Écarts et incidents

| Écart | Effet |
|---|---|
| Juge de formulation d'abord lancé sur serveur Xeon CPU : 54 s par jeton sous la charge des autres agents (load 62) | arrêté par son PID avant tout verdict ; déplacé sur la 3080 en déport partiel, revalidé sur les 80 contrôles |
| Juge 27B en déport GPU et `--parallel 2`, pas en CPU pur comme X5 | contrôles 95,0 % contre 96,7 %, écart d'un contrôle |
| Brut imatrix non passé | hors mandat de cette évaluation ; relève de G4 |
| DPO sur une seule graine d'entraînement (42) | pas de variance d'entraînement du DPO |
| Ollama de la 3080 arrêté de 13:52 à 16:29 | relancé ; copies GGUF et 27B en RAM supprimées |

## Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| SFT 42 et DPO 42 meilleurs que le brut en qualité | VÉRIFIÉ | IC sous le split test, 3 graines, `g3-eval.json` ; échouerait si l'IC couvrait 0 | une seule graine d'entraînement SFT évaluée sur test |
| Affinés moins inventifs que le brut | VÉRIFIÉ | -2,74 et -3,51 pts sur 3 graines, IC sous 0 ; juge 6/6 avant et après | un seul juge (9B), pas de contre-jugement 27B |
| Affinés préférés à l'oral | VÉRIFIÉ | net +29,6 et +35,8 sur 240 paires, juge revalidé 57/60 | une seule graine de banc (7) |
| Régression de langue sous prompt EN | VÉRIFIÉ | +2,18 et +3,31, IC au-dessus de 0 ; même sens au classifieur de trigrammes (brut 23,5 %, SFT 28,1 %, DPO 28,5 %) | cause lue sur quelques sorties, pas mesurée par sous-groupe de locale |
| Pas d'abstention nouvelle sur réponse présente | EXÉCUTÉ | 1 à 2 sur 150 par graine, comme le brut | - |
| Déterminisme du banc | VÉRIFIÉ | v1.0 identique à R2 au centième | - |
| Vitesse et RAM i5 de l'affiné | JAMAIS EXÉCUTÉ | même architecture et même taille que le brut (G2 : p90 27,3 s, inutilisable sur l'i5) | non remesuré |
| KL des GGUF affinés au f16 | JAMAIS EXÉCUTÉ | - | écart de quantification inconnu, à mesurer en G4 |
