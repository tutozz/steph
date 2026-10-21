# G5b : petit modèle des PC lents réentraîné sur les étiquettes T9

Date : 2026-10-01. Rien sur le Mac (relais ssh de fichiers de modèle et de runs seulement ; aucun corpus déplacé).

## Décision

**a-sft reste le modèle des PC lents ; G5b n'est pas adopté** : la règle T5 contre a-sft n'est pas tenue au TEST.

| Règle T5 | G5b contre a-sft (TEST) | Verdict |
|---|---|---|
| Qualité non inférieure | +0,39 [-1,60 ; +2,42] | tenu |
| Meilleur sur au moins un axe | aucun gain significatif au TEST : FR +2,07 [-0,46 ; +4,70], formulation -1,2 [-11,2 ; +8,8], Speak Bench EN +5,1 [-0,7 ; +11,4] ; le gain du juge fort (+6,9 « juste et utile », -4,9 pts d'inventions) est au DEV, le TEST lui est interdit | **non tenu** |
| Aucune régression significative | inventions A7 +3,2 [-0,4 ; +6,7] (p 0,12) ; abstentions sur réponse absente 13-15-14 contre 19-20-19 sur 20 (questions absentes -9,2 n.s.) ; mauvaise langue EN +2,2 n.s. | tenu au seuil, mais trois tendances défavorables |

Cause probable des tendances défavorables : `mix-extra` de R1 manque au mix G5b (720 lignes : questions FR et EN, dont
celles à réponse absente, fonctionnalités EN). G5b mêle donc deux changements ; l'effet propre des étiquettes T9 n'est
pas isolé. Le juge fort (DEV) et le juge A7 (TEST) divergent sur les inventions de G5b.

| Champ | Valeur |
|---|---|
| Fichier | `g5b-sft-Q4_K_M.gguf`, 222 662 112 o (taille de v1.0 et a-sft) |
| sha256 | `6a02603f95435d04ea7bbb8a67c4fce52682aa2b8a330808f103c496d81bf9b9` |
| Emplacement | hôte de la 3060 `/mnt/backup-hdd/stephbench-tmp/g5b/gguf/` ; copies 3080 `/root/steph-ft/g5b/gguf/`, i5 `/root/g5b/gguf/g5b-Q4_K_M.gguf` |
| Soupe | perte val par graine 0,332 / 0,334 / 0,345 / 0,339 ; soupe uniforme 0,313 (base 1,526) |
| Publication | aucune ; rien de public |

## Recette

Recette a-sft de G5 à l'identique (Granite 4.0 H 350M depuis P17 fusionné, SFT LoRA rang 16 de `run_k3.sh`, lr 2e-4,
3 époques, graines 42, 7, 123, 2024, soupe uniforme, GGUF Q4_K_M), données changées :

| Élément | G5 a-sft | G5b |
|---|---|---|
| Étiquettes | `final-x4-l5` (Qwen3.5 27B et 9B locaux) | `final-t9` (qwen/qwen3.8-27b, OpenRouter), `qa_train` réétiqueté compris |
| Corrections | - | `final-t9-corrections/sft.jsonl` x1 (842 lignes sur 862 après contamination) |
| Correctif de langue | recette G3b refaite sur la 3080 (94 lignes x2) | correctif G3b de l'hôte de la 3060, même recette (125 lignes x2 après contamination) |
| `mix-extra` de R1 | oui (720 lignes) | **non** : il vit sur la 3080, aucun transfert de corpus ; `--extra` vide comme G3b sur l'hôte de la 3060 |
| Mix | train 4 571, val 221 | train 4 694, val 179 |
| Machine d'entraînement | 3080 | 3060 hôte de la 3060 (torch 2.14 cu130, noyaux Triton de mamba_ssm) |

## État (reprise)

| Étape | État | Où |
|---|---|---|
| Espace de l'hôte de la 3060 : `git archive` de `f053542` + `bench/matrix/finetune/g5b/`, base P17 relayée de la 3080 (sha256 `ae5b1763…` identique), Python 3.13 autonome (src/steph exige 3.12+) | fait | hôte de la 3060 `/mnt/backup-hdd/stephbench-tmp/g5b/` |
| Mix (`chain.sh mix`) | fait : contamination par ligne -159 train, -11 val, -20 corrections, -1 correctif ; `scan` 0 cas rejeté, 0 ligne canari ; audit_pii (liste privée) : 1 chemin personnel dans une entrée reconstruite du corpus brut, ligne retirée, puis 0 ; train `94562b16…`, val `df37c596…` | `g5b/mix/`, `logs/mix-sha.txt` |
| SFT 4 graines (`chain.sh sft`) | fait (graine 123 relancée : disque plein par un autre agent à l'époque 2,1) | `g5b/a/` |
| Soupe, GGUF (`chain.sh soup`) | fait | `g5b/gguf/` |
| DEV et TEST, juge A7, Speak Bench (`eval_3080.sh`) | fait ; Ollama arrêté à 06:55, relancé à 07:42 | 3080 `/root/steph-ft/g5b/` |
| Juge fort DEV (`useful.sh`) | fait, 0,2832 $ ; clé effacée | 3080 `/root/steph-ft/g5b/useful/`, `useful/` ici |
| Formulation 27B (`style_xeon.sh`) | fait | serveur Xeon `/root/steph-ft/g5b/style/` |
| i5 (`i5.sh a-sft g5b`, puis `i5.sh v10 g5b`) | fait | i5 `/root/g5b/res/`, `eval/i5-summary.json` |

Piège : sans `mamba_ssm` le venv de l'hôte de la 3060 prend le balayage torch de référence de transformers (OOM, 24 Go demandés
à la validation) ; `g5b/pylib` porte mamba_ssm 2.3.2.post1 sans noyaux CUDA (Triton seul, `__init__` patché comme sur la
3080) et einops, par PYTHONPATH, sans toucher au venv partagé.

## DEV (banc v3 `dev.json`, 3 graines, 3080 CUDA `9588757` ; v1.0 et a-sft : runs de G5)

| Modèle | Qualité | FR / EN | Questions présente / absente | Abstentions présente / absente | Note de production (HEAD) | Inventions A7 | Mauvaise langue FR / EN |
|---|---|---|---|---|---|---|---|
| v1.0 | 50,0 | 49,6 / 50,5 | 49,1 / 54,5 | 8-9-8 / 11-10-10 | 77,4 | 31,5 % | 8,0 / 9,7 % |
| a-sft | 53,7 | 50,1 / 57,3 | 58,7 / 59,1 | 3-7-5 / 12-14-13 | 78,3 | 29,9 % | 7,9 / 4,3 % |
| G5b | 52,9 | 53,5 / 52,2 | 61,8 / 36,4 | 6-5-5 / 8-8-8 | 77,5 | 25,1 % | 5,8 / 3,4 % |

| Écart apparié (IC 95 %) | Qualité | FR | EN | Inventions A7 | Questions présentes |
|---|---|---|---|---|---|
| G5b - v1.0 | +2,81 [-0,03 ; +5,59] | **+3,88** | +1,74 | **-6,38 [-11,28 ; -1,55]** | **+12,75** |
| a-sft - G5b | +0,84 [-1,68 ; +3,33] | **-3,45** | **+5,12 [+1,92 ; +8,35]** | **+4,80 [+0,43 ; +9,20]** | -3,19 |

- Juge A7 de G5b : 3 graines sur la 3080, contrôles 6/6 FR et EN avant et après ; ceux de G5 : graines 7 et 42 sur la 3060 (Vulkan), 123 sur la 3080.
- Note de production recalculée pour les trois modèles avec `score_production.py` du HEAD (aides D5 et D6) : 77 à 78 contre 58 à 61 dans G5.

### Juge fort DEV (« juste et utile », `google/gemma-4-31b-it`, graine 7)

DEV entier, 857 évaluations notées pour les trois modèles ; contrôles plantés 11/15 exacts, 15/15 à un barreau (comme T9).

| Modèle | Juste et utile | FR / EN | Inventions |
|---|---|---|---|
| v1.0 | 47,3 | 47,5 / 47,0 | 28,7 % |
| a-sft | 51,1 | 48,0 / 54,3 | 29,6 % |
| G5b | **58,1** | 56,8 / 59,4 | **24,7 %** |

| Écart apparié (bootstrap 2 000) | Juste et utile | Inventions |
|---|---|---|
| G5b - a-sft | **+6,94 [+4,35 ; +9,80]** | **-4,90 [-8,28 ; -1,40]** |
| G5b - v1.0 | **+10,82 [+7,88 ; +13,97]** | **-3,97 [-7,35 ; -0,35]** |
| a-sft - v1.0 | **+3,88 [+1,08 ; +6,51]** | +0,93 [-2,57 ; +4,55] |

Sous-échantillon stratifié de T9 (152) : G5b 61,2, a-sft 52,3, v1.0 49,3 (T9 : v1.0 46,8 au harnais générique).
Dépense : 0,2832 $ (journal `useful/spend.jsonl`), compte 2,641 $ avant. **TEST non jugé** : `judge_useful_v3.py`
refuse le split TEST (invariant de T9 : le TEST ne part jamais chez un fournisseur).

## TEST (banc v3 `test.json` `705fdcb9`, harnais affiné L5, 3 graines, 3080 CUDA `9588757`, lu une fois)

Écarts appariés par cas, bootstrap 10 000 tirages (`g5_eval.py` de G5, outils du HEAD). v1.0 et a-sft : runs et verdicts de G5.

| Axe | v1.0 | a-sft | G5b | G5b - a-sft (IC 95 %) | G5b - v1.0 (IC 95 %) |
|---|---|---|---|---|---|
| Qualité `score_v3`, 654 cas | 50,6 | 53,0 | **53,4** | +0,39 [-1,60 ; +2,42] | **+2,74 [+0,51 ; +4,99]** |
| Note de production (HEAD, D5 D6) | 65,5 | 65,5 | 65,5 | +0,01 [-1,40 ; +1,41] | 0,00 [-1,44 ; +1,44] |
| Inventions A7 9B, 3 graines (2 478 verdicts) | 30,6 % | **26,0 %** | 29,2 % | +3,19 [-0,36 ; +6,70], p 0,12 | -1,41 [-5,21 ; +2,34] |
| Douteux A7 | 9,2 % | 9,7 % | 8,5 % | - | - |
| Formulation à l'oral, juge 27B, net (240 paires) | - | - | - | -1,2 [-11,2 ; +8,8] (75 contre 78, 87 égalités) | **+18,3 [+8,3 ; +27,9]** (97 contre 53) |
| Formulation, prompt FR / EN | - | - | - | 0,0 / -2,3 | **+31,2** / +7,6 |
| Résumés | 51,1 | 53,8 | 54,1 | +0,26 | **+2,98** |
| Questions (70 cas) | 46,9 | 46,2 | 47,7 | +1,47 [-5,99 ; +9,09] | +0,75 |
| Questions présente / absente | 47,0 / 46,7 | 45,3 / 48,3 | 51,1 / 39,2 | +5,72 / -9,17 [-22,5 ; +3,3] | +4,06 / -7,50 |
| Abstentions présente (sur 50) / absente (sur 20), par graine | 8-9-9 / 19-19-18 | 10-8-9 / 19-20-19 | 7-8-9 / **13-15-14** | - | - |
| FR / EN | 49,8 / 51,5 | 50,5 / 55,4 | 52,6 / 54,2 | +2,07 [-0,46 ; +4,70] / -1,29 | +2,78 [0,00 ; +5,56] / +2,69 |
| Mauvaise langue, prompt FR | 8,96 % | 7,02 % | 5,81 % | -1,21 | **-3,15 [-5,81 ; -0,56]** |
| Mauvaise langue, prompt EN | 12,27 % | 4,36 % | 6,54 % | +2,18 [-0,16 ; +4,60] | **-5,73 [-8,96 ; -2,50]** |
| Sortie FR sous prompt EN, cas à sortie FR | 39,5 % | 12,6 % | 18,7 % | +6,12 [-2,72 ; +14,97] | **-20,75** |
| Speak Bench, FR (62 cas) | 43,2 | 41,5 | 43,1 | +1,59 [-6,77 ; +9,33] | -0,08 |
| Speak Bench, EN (62 cas) | 47,2 | 48,3 | 53,4 | +5,08 [-0,73 ; +11,37] | +6,21 [-2,42 ; +14,84] |
| Speak Bench, interdits FR / EN | 4,8 / 3,2 % | 4,8 / 1,6 % | 4,8 / 1,6 % | 0 / 0 | 0 / -1,6 |
| Qualité par graine 7 / 42 / 123 | 50,6 / 50,5 / 50,8 | 52,4 / 53,1 / 53,5 | 53,8 / 53,5 / 52,8 | - | - |

- Juge A7 : Qwen3.5 9B `03b74727`, 3080, une carte pour les 3 graines, contrôles 6/6 FR et EN avant et après (DEV et TEST), 0 erreur de juge au TEST.
- Formulation : juge Qwen3.5 27B `84b5f7f1`, serveur Xeon CPU, un slot, `--cache-ram 0`, graine 7, paires par hachage ; contrôles plantés X5 77/80 avant et après ; paires instables (comptées en égalité) : 70 (contre a-sft), 67 (contre v1.0).
- Speak Bench : protocole steph, température 0, 3080, `--cache-ram 0` ; a-sft et v1.0 : résultats de G5.

## i5-7200U (production : `-c 8192 --parallel 2 -t 4 --cache-ram 0 -ub 512 -b 512`, b11205)

a-sft et G5b alternés, puis v1.0 (passes G5b reprises) ; charge < 0,3 et aucun `llama-server` avant chaque passe.

| Mesure | v1.0 (passes 1 / 2) | a-sft | G5b |
|---|---|---|---|
| 36 cas, 1er jeton médiane | 0,65 / 0,63 s | 0,62 / 0,62 s | 0,64 / 0,63 s |
| 36 cas, 1er jeton p90 | 2,33 / 2,37 s | 2,39 / 2,37 s | 2,33 / 2,34 s |
| RAM pic `llama-server` | 565 / 564 Mo | 563 / 563 Mo | 564 / 563 Mo |
| 90 questions dev à froid, 1er jeton médiane / p90 | 2,27 / 7,22 et 2,23 / 7,28 s | 2,23 / 7,21 et 2,25 / 7,28 s | 2,26 / 7,14 et 2,27 / 7,18 s |
| Génération | 59,8 / 59,3 j/s | 58,3 / 59,7 j/s | 59,3 / 59,5 j/s |

Même architecture, même quantification, même taille : aucune différence attendue ni mesurée.

## Écarts

| Écart | Effet |
|---|---|
| `mix-extra` de R1 absent (aucun transfert de corpus depuis la 3080) | deux changements confondus ; moins d'abstentions sur réponse absente, EN moins bon au DEV |
| Correctif de langue de G3b (hôte de la 3060) au lieu de celui de G5 (3080) | même recette, autre tirage : 125 lignes contre 94 |
| Entraînement sur la 3060 (torch 2.14, noyaux Triton de mamba_ssm hors venv) au lieu de la 3080 (torch 2.11) | numérique différente, recette identique |
| Juge fort sur le DEV seulement | le TEST est refusé par l'outil ; aucune mesure d'inventions par le juge fort au TEST |
| Juge A7 DEV de G5 sur deux cartes (3060 et 3080), G5b sur la 3080 seule | écarts DEV d'inventions à lire avec prudence ; TEST entièrement sur la 3080 |

Fichiers : `eval/g5b-eval-dev.json`, `eval/g5b-eval-test.json`, `eval/speak-test.txt`, `eval/i5-summary.json`,
`useful/` (contrôles, rapport du sous-échantillon, journal de dépense, `pair-dev.json` par `useful_pair.py`).
Hors dépôt : hôte de la 3060 `/mnt/backup-hdd/stephbench-tmp/g5b/` (mix, adaptateurs, GGUF), 3080 `/root/steph-ft/g5b/`
(runs, verdicts, Speak Bench, juge fort), serveur Xeon `/root/steph-ft/g5b/` (formulation), i5 `/root/g5b/`.
