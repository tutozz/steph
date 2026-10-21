# G5c : G5b refait à recette identique à a-sft, pour isoler l'effet des étiquettes T9

Date : 2026-10-01. Rien sur le Mac (relais ssh de fichiers de modèle et de runs seulement ; aucun corpus déplacé par cette tâche).

## Décision

**a-sft reste le modèle des PC lents ; G5c n'est pas adopté** : la règle T5 contre a-sft n'est pas tenue au TEST, à cause
d'une régression significative de la langue sous prompt anglais.

| Règle T5 | G5c contre a-sft (TEST) | Verdict |
|---|---|---|
| Qualité non inférieure | +0,14 [-1,86 ; +2,14] | tenu |
| Meilleur sur au moins un axe | **juste et utile (juge fort) +4,13 [+1,99 ; +6,35]** ; **questions à réponse absente +19,2 [+5,8 ; +32,5]** ; inventions juge fort -3,83 [-6,43 ; -1,07] par évaluation | tenu |
| Inventions, juge fort et A7 au même poids | combiné -2,93 [-5,91 ; +0,22] (A7 -2,70 n.s., juge fort -3,15 n.s. sur les 825 évaluations `reaches_model`) | ni gain ni perte significatif |
| Aucune régression significative | **mauvaise langue sous prompt EN 7,75 % contre 4,36 % : +3,39 [+1,13 ; +5,81]** ; sortie FR sous prompt EN +12,9 [+4,8 ; +21,1] ; abstentions, Speak Bench, note de production, formulation : rien de significatif | **non tenu** |

Effet propre des étiquettes T9 (G5c ne diffère de a-sft que par elles, plus le tirage du correctif de langue) :

- gain net au juge fort, au TEST : +4,1 en « juste et utile », moins d'inventions (-3,8 pts par évaluation) ;
- les abstentions sur réponse absente remontent au-dessus de a-sft (27-26-28 contre 19-20-19 sur 40) : le recul de G5b venait bien de l'absence du `mix-extra` ;
- le recul en anglais persiste (EN -1,9 n.s., mauvaise langue EN +3,4 significatif) : il ne venait pas du `mix-extra`.

Cause possible du recul EN, non vérifiée : le correctif de langue n'est pas celui de a-sft (tirage G3b de l'hôte de la
3060, 125 lignes, contre celui de G5 sur la 3080, 94 lignes), ou les étiquettes T9 elles-mêmes. Le seul écart de recette
restant est ce correctif ; le refaire avec celui de G5 trancherait.

| Champ | Valeur |
|---|---|
| Fichier | `g5c-a-sft-Q4_K_M.gguf`, 222 662 112 o (taille de v1.0 et a-sft) |
| sha256 | `8109d144444d38a37332182a70a74ad486e0cc1c0ce2b551eac77e6eb8e23c2d` |
| Emplacement | 3080 `/root/steph-ft/g5c/gguf/` ; copie i5 `/root/g5c/gguf/g5c-Q4_K_M.gguf` |
| Soupe | perte val par graine 0,357 / 0,369 / 0,375 / 0,358 (graines 42, 7, 123, 2024) |
| Dépense OpenRouter | **0,5324 $** sur un plafond de 0,6 $ (journal `useful/spend.jsonl`, trace `decision-test` en tête) ; compte 2,924 $ avant |
| Publication | aucune ; rien de public |

## Recette

Recette a-sft de G5 (Granite 4.0 H 350M depuis P17 fusionné `/root/steph-ft/r1/base-p17`, `run_k3.sh` : SFT LoRA
rang 16, lr 2e-4, 3 époques, graines 42 et 7 puis 123 et 2024 deux à deux, soupe uniforme, GGUF Q4_K_M) ; seules les
étiquettes changent.

| Élément | G5 a-sft | G5b | G5c |
|---|---|---|---|
| Étiquettes | `final-x4-l5` | `final-t9` | `final-t9` |
| Corrections T9 | - | x1 | x1 (842 lignes après contamination) |
| `mix-extra` de R1 | oui (720 lignes) | **non** | **oui**, `ft/data/mix-extra-r1`, sha256 identiques à ceux de la 3080 (`5a513601…`, `cb39f688…`) |
| Correctif de langue | G5 (3080, 94 lignes x2) | G3b de l'hôte de la 3060 (125 x2) | G3b de l'hôte de la 3060 (125 x2) : celui de G5 n'est pas sur cette machine |
| Mix | train 4 571, val 221 | train 4 694, val 179 | **train 5 409 `9ee83dd2…`, val 215 `b1d7ada3…`** |
| Machine d'entraînement | 3080 | 3060 | **3080**, comme a-sft (mix copié et audité par l'utilisateur dans `/root/steph-ft/data/mix-g5c`, sha256 vérifiés) |

## État (reprise)

| Étape | État | Où |
|---|---|---|
| Option `--decision-test` du juge fort (TDD) | fait, `e6d0785` | `bench/matrix/v3/tools/judge_useful_v3.py` |
| Mix (`chain.sh mix`, hôte de la 3060) | fait : chaîne R1 4 482 / 226 (dont `mix-extra` 720 / 36), contamination par ligne -164 train, -11 val, -20 corrections, -1 correctif ; audit_pii : 1 ligne retirée, puis 0 ; `scan` 0 cas rejeté, 0 ligne canari | 3060 `/mnt/backup-hdd/stephbench-tmp/g5c/mix/` |
| SFT, soupe, GGUF (`train_3080.sh`) | fait, 15:04 - 16:31 ; la 3060 occupée par G3c a été abandonnée (SFT jamais parti, PID 29365 et 33883 arrêtés) | 3080 `/root/steph-ft/g5c/a/`, `gguf/` |
| DEV, TEST, juge A7, Speak Bench (`eval_3080.sh`) | fait, 16:31 - 17:44 ; a-sft et v1.0 regénérés : réponses identiques aux runs de G5 (DEV et TEST, 3 graines), verdicts A7 de G5 repris ; Ollama arrêté 15:04, relancé 17:44 ; **rearrêté à 19:22 par un autre chantier** (juge Qwen 9B sur la carte), laissé arrêté | 3080 `/root/steph-ft/g5c/` |
| Analyse appariée (`g5_eval.py`) | fait | `eval/g5c-eval-dev.json`, `eval/g5c-eval-test.json` |
| Juge fort TEST de décision (`useful.sh 0.6`) | fait, 3 634 réponses, 0,5324 $ ; clé effacée | `useful/`, `eval/inv-combined-test.json` (`g5c_decision.py`) |
| Formulation 27B (`style_xeon.sh`) | fait, 18:20 - 20:18 ; serveur 27B arrêté | serveur Xeon `/root/steph-ft/g5c/style/` |
| i5 (`i5.sh a-sft g5c`, puis `i5.sh v10 g5c`) | fait | i5 `/root/g5c/res/`, `eval/i5-summary.json` |

## DEV (banc v3 `dev.json`, 3 graines, 3080 CUDA `9588757`)

| Modèle | Qualité | FR / EN | Questions présente / absente | Abstentions présente (/100) / absente (/40) | Note de production (HEAD) | Inventions A7 | Mauvaise langue FR / EN |
|---|---|---|---|---|---|---|---|
| v1.0 | 50,0 | 49,6 / 50,5 | 49,1 / 54,5 | 8-9-8 / 11-10-10 | 77,4 | 31,5 % | 8,0 / 9,7 % |
| a-sft | 53,7 | 50,1 / 57,3 | 58,7 / 59,1 | 3-7-5 / 12-14-13 | 78,3 | 29,9 % | 7,9 / 4,3 % |
| G5c | 53,0 | 53,3 / 52,8 | 60,5 / 45,5 | 6-7-7 / 11-8-11 | 78,1 | **22,6 %** | 4,2 / 5,3 % |

| Écart apparié (IC 95 %) | Qualité | FR | EN | Inventions A7 | Mauvaise langue FR |
|---|---|---|---|---|---|
| G5c - v1.0 | **+2,99 [+0,25 ; +5,67]** | **+3,68** | +2,30 | **-8,86 [-13,63 ; -4,40]** | **-3,81** |
| G5c - a-sft | -0,66 [-2,94 ; +1,66] | **+3,25** | **-4,57 [-7,52 ; -1,60]** | **-7,28 [-11,34 ; -3,31]** | **-3,69** |

Juge A7 de G5c : 3 graines sur la 3080, contrôles 6/6 FR et EN avant et après ; ceux de G5 : graines 7 et 42 sur la 3060 (Vulkan), 123 sur la 3080.

## TEST (banc v3 `test.json` `705fdcb9`, harnais affiné L5, 3 graines, 3080 CUDA `9588757`, lu une fois)

Écarts appariés par cas, bootstrap 10 000 tirages (`g5_eval.py` de G5, outils du HEAD). a-sft et v1.0 regénérés dans
cette session, identiques aux runs de G5 ; verdicts A7 de G5.

| Axe | v1.0 | a-sft | G5c | G5c - a-sft (IC 95 %) | G5c - v1.0 (IC 95 %) |
|---|---|---|---|---|---|
| Qualité `score_v3`, 654 cas | 50,6 | 53,0 | **53,2** | +0,14 [-1,86 ; +2,14] | **+2,49 [+0,20 ; +4,75]** |
| Note de production (HEAD, D5 D6) | 65,5 | 65,5 | 65,5 | -0,03 [-1,40 ; +1,35] | -0,04 [-1,51 ; +1,40] |
| **Juste et utile, juge fort, graine 7** (1 307 évaluations) | 46,9 | 52,0 | **56,2** | **+4,13 [+1,99 ; +6,35]** | **+9,30 [+7,02 ; +11,55]** |
| Juste et utile FR / EN | 45,9 / 47,8 | 50,6 / 53,5 | 54,5 / 57,9 | - | - |
| Inventions juge fort, toutes évaluations | 30,2 % | 28,2 % | **24,4 %** | **-3,83 [-6,43 ; -1,07]** | **-5,81 [-8,65 ; -2,83]** |
| Inventions A7 9B, 3 graines (2 478 verdicts) | 30,6 % | 26,0 % | 23,3 % | -2,74 [-6,13 ; +0,56], p 0,22 | **-7,34 [-10,98 ; -3,67]** |
| Inventions combinées A7 + juge fort, même poids (825 évaluations `reaches_model`) | 32,0 % | 28,5 % | 25,6 % | -2,93 [-5,91 ; +0,22] | **-6,38 [-9,60 ; -3,07]** |
| Douteux A7 | 9,2 % | 9,7 % | 8,8 % | - | - |
| Formulation à l'oral, juge 27B, net (240 paires) | - | - | - | +3,3 [-6,2 ; +12,9] (74 contre 66, 100 égalités) | **+16,7 [+7,1 ; +26,2]** (95 contre 55) |
| Résumés | 51,1 | 53,8 | 53,1 | -0,66 | +2,05 |
| Questions (70 cas) | 46,9 | 46,2 | 53,1 | +6,87 [-0,44 ; +14,37] | +6,15 |
| Questions présente / absente | 47,0 / 46,7 | 45,3 / 48,3 | 47,3 / **67,5** | +1,94 / **+19,17 [+5,83 ; +32,50]** | +0,28 / **+20,83** |
| Abstentions présente (/100) / absente (/40), par graine | 8-9-9 / 19-19-18 | 10-8-9 / 19-20-19 | 10-13-11 / **27-26-28** | - | - |
| FR / EN | 49,8 / 51,5 | 50,5 / 55,4 | 52,7 / 53,6 | +2,17 [-0,36 ; +4,76] / -1,89 [-4,38 ; +0,56] | +2,88 / +2,09 |
| Mauvaise langue, prompt FR | 8,96 % | 7,02 % | 5,17 % | -1,86 [-4,20 ; +0,40] | **-3,79 [-6,38 ; -1,37]** |
| **Mauvaise langue, prompt EN** | 12,27 % | 4,36 % | 7,75 % | **+3,39 [+1,13 ; +5,81]** | **-4,52 [-7,43 ; -1,78]** |
| Sortie FR sous prompt EN, cas à sortie FR (98) | 39,5 % | 12,6 % | 25,5 % | **+12,93 [+4,76 ; +21,09]** | **-13,95 [-24,15 ; -3,74]** |
| Speak Bench, FR (62 cas) | 43,2 | 41,5 | 46,1 | +4,60 [-4,97 ; +13,44] | +2,93 [-6,83 ; +12,55] |
| Speak Bench, EN (62 cas) | 47,2 | 48,3 | 50,1 | +1,85 [-4,60 ; +8,66] | +2,98 [-5,11 ; +10,94] |
| Speak Bench, interdits FR / EN | 4,8 / 3,2 % | 4,8 / 1,6 % | 4,8 / 1,6 % | 0 / 0 | 0 / -1,6 |
| Qualité par graine 7 / 42 / 123 | 50,6 / 50,5 / 50,8 | 52,4 / 53,1 / 53,5 | 53,6 / 52,9 / 53,0 | - | - |

- Juge A7 : Qwen3.5 9B `03b74727`, 3080, contrôles 6/6 FR et EN avant et après (DEV et TEST), 0 erreur de juge au TEST.
- Juge fort : `google/gemma-4-31b-it` sans raisonnement, `judge_useful_v3.py --split test --decision-test` (décision
  utilisateur du 2026-10-01 : TEST permis pour juger les candidats d'une décision, jamais pour étiqueter) ; contrôles
  plantés 11/15 exacts, 15/15 à un barreau (comme T9 et G5b) ; 1 erreur de juge (G5c).
  Écarts « juste et utile » et inventions par évaluation (`useful_pair.py`, bootstrap 2 000) ; combiné par cas (`g5c_decision.py`).
- Formulation : juge Qwen3.5 27B `84b5f7f1`, serveur Xeon CPU, un slot, `--cache-ram 0`, graine 7, paires par hachage ;
  contrôles plantés X5 77/80 avant et après ; biais de position 48,7 % ; paires instables (comptées en égalité) : 77 (contre a-sft), 64 (contre v1.0) ; formulation FR / EN contre a-sft +3,6 / +3,1, contre v1.0 **+28,7** / +5,6.
- Speak Bench : protocole steph, température 0, 3080, `--cache-ram 0` ; a-sft et v1.0 rejoués dans cette session, scores identiques à G5.

## i5-7200U (production : `-c 8192 --parallel 2 -t 4 --cache-ram 0 -ub 512 -b 512`, b11205)

a-sft et G5c alternés, puis v1.0 (passes G5c reprises) ; charge < 0,3 et aucun `llama-server` avant chaque passe.

| Mesure | v1.0 (passes 1 / 2) | a-sft | G5c |
|---|---|---|---|
| 36 cas, 1er jeton médiane | 0,67 / 0,62 s | 0,67 / 0,66 s | 0,65 / 0,67 s |
| 36 cas, 1er jeton p90 | 2,32 / 2,39 s | 2,31 / 2,32 s | 2,39 / 2,32 s |
| RAM pic `llama-server` | 564 / 564 Mo | 564 / 563 Mo | 563 / 565 Mo |
| 90 questions dev à froid, 1er jeton médiane / p90 | 2,27 / 7,25 et 2,26 / 7,21 s | 2,27 / 7,22 et 2,27 / 7,18 s | 2,25 / 7,25 et 2,29 / 7,20 s |
| Génération (36 cas) | 59,5 / 59,1 j/s | 59,6 / 59,9 j/s | 60,1 / 59,2 j/s |

Même architecture, même quantification, même taille : aucune différence attendue ni mesurée.

## Écarts

| Écart | Effet |
|---|---|
| Correctif de langue de G3b (hôte de la 3060) au lieu de celui de G5 (3080) | dernier écart de recette avec a-sft ; candidat à la régression EN |
| Mix construit sur la 3060, entraînement sur la 3080 (copie par l'utilisateur, sha256 vérifiés) | aucun sur la recette ; le corpus T9 dérivé est désormais sur toutes les machines d'entraînement |
| Juge fort sur la graine 7 seule ; A7 sur 3 graines | le combiné mêle un taux sur 3 graines et un indicateur sur une |
| Juge A7 DEV de G5 sur deux cartes, G5c sur la 3080 seule | écarts DEV d'inventions à lire avec prudence ; TEST entièrement sur la 3080 |
| Dénominateurs des abstentions : 100 évaluations présentes et 40 absentes (50 et 20 cas, deux langues) | G5 et G5b écrivaient « sur 50 » et « sur 20 » : c'étaient des cas, les comptes sont des évaluations |

Fichiers : `eval/` (analyses DEV et TEST, Speak Bench, inventions combinées, i5), `useful/` (contrôles, rapport, paires,
journal de dépense), `useful_pair.py`, `g5c_decision.py`. Pilotes : `bench/matrix/finetune/g5c/`. Hors dépôt : 3060
`/mnt/backup-hdd/stephbench-tmp/g5c/` (mix), 3080 `/root/steph-ft/g5c/` (adaptateurs, GGUF, runs, verdicts, juge fort),
serveur Xeon `/root/steph-ft/g5c/` (formulation), i5 `/root/g5c/`.

## Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| G5c régresse en langue sous prompt EN contre a-sft | VÉRIFIÉ | `eval/g5c-eval-test.json`, +3,39 [+1,13 ; +5,81], 3 graines ; échouerait si l'IC touchait 0 | cause : correctif de langue ou étiquettes T9, non tranché |
| G5c plus « juste et utile » que a-sft au TEST | VÉRIFIÉ | `useful/pair-test.json`, +4,13 [+1,99 ; +6,35] ; contrôles plantés 15/15 à un barreau | une graine ; un seul juge fort ; bootstrap par évaluation, pas par cas |
| Le `mix-extra` explique les abstentions perdues de G5b | VÉRIFIÉ | absente 27-26-28 (G5c) contre 13-15-14 (G5b), questions absentes +19,2 [+5,8 ; +32,5] contre a-sft | G5b et G5c entraînés sur deux cartes différentes |
| a-sft et v1.0 rebanqués à l'identique | VÉRIFIÉ | `run.done` : IDENTIQUE dev et test, 3 graines ; Speak Bench égal à G5 | - |
| Inventions : pas d'écart significatif entre G5c et a-sft au poids égal des deux juges | VÉRIFIÉ | `eval/inv-combined-test.json`, -2,93 [-5,91 ; +0,22] | juge fort sur la graine 7 seule |
| `--decision-test` refuse le TEST sans l'option et trace au journal | VÉRIFIÉ | `test_judge_useful_v3.py` (16 tests) ; `useful/spend.jsonl` ligne 1 | - |
| Vitesse et RAM i5 égales | EXÉCUTÉ | `eval/i5-summary.json`, 2 passes | RAM de steph et Piper non remesurée |
| Formulation égale à a-sft, meilleure que v1.0 | VÉRIFIÉ | `eval/g5c-eval-test.json` style : +3,3 [-6,2 ; +12,9] et +16,7 [+7,1 ; +26,2] ; contrôles 77/80 avant et après | une graine ; 77 paires instables ; jamais entendu en synthèse vocale |
