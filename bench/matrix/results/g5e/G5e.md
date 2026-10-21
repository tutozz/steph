# G5e : étiquettes T9 de mauvaise langue remplacées par X4-L5, part de prompts EN rétablie

Date : 2026-10-02. Rien sur le Mac : seuls des agrégats (comptes, empreintes, taux) en sont revenus ; le corpus n'a pas
quitté la 3080.

## Décision

**Le TEST n'est pas passé : la condition n'est pas tenue sur la qualité anglaise.** Le correctif ramène la langue sous
prompt anglais au niveau d'a-sft. Il ne ramène pas la qualité EN, qui reste significativement sous a-sft, comme pour G5c et
G5d. Aucune dépense OpenRouter ; **a-sft reste le modèle des PC lents**.

| DEV, 3 graines (429 cas x 2 langues) | a-sft | G5c | G5e | G5e - a-sft (IC 95 %) | G5e - G5c (IC 95 %) |
|---|---|---|---|---|---|
| Mauvaise langue, prompt EN (271 évaluations) | 4,31 % | 5,29 % | **3,81 %** | -0,49 [-2,71 ; +1,72] | -1,48 [-3,81 ; +0,74] |
| Sortie FR sous prompt EN (62 évaluations) | 16,67 % | 22,58 % | **13,98 %** | -2,69 [-11,83 ; +5,91] | -8,60 [-17,74 ; +0,00] |
| **Qualité EN** | 57,3 | 52,8 | 52,8 | **-4,47 [-7,64 ; -1,30]** | +0,10 [-2,37 ; +2,60] |
| Mauvaise langue, prompt FR | 7,87 % | 4,18 % | 4,31 % | **-3,57 [-7,13 ; -0,12]** | +0,12 [-2,34 ; +2,58] |
| Qualité FR | 50,1 | 53,3 | 52,6 | +2,56 [-0,59 ; +5,70] | -0,69 [-3,33 ; +1,97] |
| Qualité `score_v3` | 53,7 | 53,0 | 52,7 | -0,96 [-3,44 ; +1,55] | -0,30 [-2,15 ; +1,53] |
| Note de production (HEAD) | 78,3 | 78,1 | 78,3 | -0,02 [-1,37 ; +1,30] | +0,24 [-0,61 ; +1,13] |
| **Inventions A7 9B**, 3 graines (1 613 verdicts) | 29,9 % | 22,6 % | **23,8 %** | **-6,10 [-10,29 ; -1,80]** | +1,18 [-2,42 ; +4,65] |
| Questions présente / absente | 58,7 / 59,1 | 60,5 / 45,5 | 61,8 / 54,5 | +3,10 / -4,55 (n.s.) | +1,23 / +9,09 [-1,52 ; +22,73] |
| Abstentions présente (/100) / absente (/40) | 3-7-5 / 12-14-13 | 6-7-7 / 11-8-11 | 6-6-8 / 11-12-12 | - | - |
| Qualité par graine 7 / 42 / 123 | 53,4 / 54,2 / 53,5 | 53,2 / 53,0 / 52,9 | 53,4 / 52,6 / 52,2 | - | - |

Lecture :

- **La langue EN est réparée.** La mauvaise langue sous prompt EN passe sous a-sft (3,81 contre 4,31 %, n.s.). La sortie FR
  sous prompt EN baisse de 8,6 points contre G5c, borne haute à 0. G5c et G5d n'avaient aucun rapprochement d'a-sft.
- **La qualité EN ne bouge pas** : 52,8 pour G5c et G5e, 53,6 pour G5d. L'écart avec a-sft (-4,47) n'est donc pas un effet de langue.
  Il vient d'autre chose dans les étiquettes T9 anglaises (`en_summary`), qui ne sont presque pas touchées ici (0 ligne EN
  remplacée).
- **Le gain T9 tient en partie** : inventions A7 -6,10 significatif contre a-sft, mauvaise langue FR -3,57 significatif.
  La qualité FR (+2,56) n'est plus significative (G5c +3,25).
- La condition de passage au TEST demandait « l'anglais rejoint a-sft, aucun écart significatif » : la qualité EN la fait
  échouer. Au TEST, G5c avait une qualité EN à -1,89 n.s. alors que son DEV la donnait à -4,57 significatif. Le DEV de G5e
  ne dit donc pas que le TEST échouerait ; il ne permet pas de le lancer sous la règle donnée.

| Champ | Valeur |
|---|---|
| Fichier | `g5e-a-sft-Q4_K_M.gguf`, 222 662 112 o |
| sha256 | `84cd81ee4dc92c6c59d265c79b1197626f5137c99637fd7d31b7109980e5ef6f` |
| Emplacement | 3080 `/root/steph-ft/g5e/gguf/` |
| Soupe | perte val par graine 0,400 / 0,396 / 0,404 / 0,406 (graines 42, 7, 123, 2024) ; val modifiée (10 étiquettes), non comparable à G5d |
| Dépense OpenRouter | **0 $** (TEST non passé) ; budget restant inchangé |
| Publication | aucune ; rien de public |

## Suite possible (non lancée)

1. Passer le TEST malgré la qualité EN au DEV, sur décision utilisateur : le blocage de G5c au TEST était la mauvaise
   langue EN, que G5e répare au DEV. Coût : environ 0,2 $ de juge fort (seules les réponses G5e sont nouvelles) et 3 h.
2. Isoler la qualité EN : G5e avec les `en_summary` de X4-L5 à la place de T9 (les autres étiquettes T9 gardées). Si la
   qualité EN rejoint a-sft, l'apport T9 se limite au français et aux corrections.

## Mélange (`g5e/mix.sh`, `g5e/g5e_mix.py`)

Départ : `mix-g5d` (train 5 347 `18bb5c29…`, val 215 `b1d7ada3…`). Langue classée par `lang_v3.classify` (mots-outils de
R3-T2) ; langue du prompt = celle du message système (toujours nette sur ce mélange).

Règle : une ligne T9 (hors `mix-extra` de R1 et correctif de langue) change si son étiquette est **nettement** dans l'autre
langue que le prompt, si `final-x4-l5` porte la même entrée sous le même message système, et si l'étiquette X4-L5 n'est pas
elle-même dans la mauvaise langue. Les indécis restent.

| Mesure | train | val |
|---|---|---|
| Lignes changées (étiquette X4-L5 reprise) | **94** (`fr_summary` 78, `detail` 10, corrections 6 ; toutes sous prompt FR) | 10 (`fr_summary` 6, `detail` 4) |
| Mauvaise langue gardée, X4-L5 aussi dans la mauvaise langue | 97 (`detail` 80, `en_summary` 10, `fr_summary` 2, corrections 5) | 12 (`detail`) |
| Mauvaise langue gardée, sans entrée X4-L5 | 20 (`fr_summary` 9, `qa` 4, corrections 5, `en_summary` 2) | 0 |
| Étiquettes « prompt FR, sortie EN » | 201 -> **107** (a-sft : 130) | 22 -> 12 |
| Étiquettes « prompt EN, sortie FR » | 22 -> 22 | 0 |
| Corrections T9 sous prompt EN, hors étiquette FR | 138, **x3** (+276 lignes en fin de fichier) | - |
| Part de prompts EN | 33,46 % -> **36,72 %** (a-sft 36,3 %) | 24,19 % (inchangée) |
| Autres lignes, même ordre | 5 253, empreinte `081ae1f1…` identique avant et après | 205, `d7b364a0…` identique |
| `leak_check drop` | 0 ligne retirée sur 5 623 | 0 sur 215 |
| `leak_check scan` | 0 cas rejeté, 0 ligne canari | idem |
| `audit_pii` | TOTAL 0 (liste de noms copiée chmod 600, effacée par `shred`) | idem |
| Mélange G5e | **5 623 `f7b1707b…`** | **215 `22fbc263…`** |

Choix du rééquilibrage : duplication des corrections EN plutôt que retrait de corrections FR. Retirer 419 corrections FR
sur 702 aurait coûté le signal T9 en français ; x2 n'aurait donné que 35,2 %. Deux corrections EN restées à étiquette
française ne sont pas dupliquées (premier essai interrompu à 10:12 pour cette raison : elles portaient « prompt EN, sortie
FR » de 22 à 26).

Fichiers : `eval/mix-relabel.json` (comptes), `eval/mix-sha.txt` (empreintes, audit, fuite). Tests : `test_g5e_mix.py`
(7 tests, mélange synthétique, exécutés sur la 3080).

## État (reprise)

| Étape | État | Où |
|---|---|---|
| Mélange (`g5e/mix.sh`) | fait, 10:20 | 3080 `/root/steph-ft/data/mix-g5e` |
| SFT, soupe, GGUF (`g5e/train_3080.sh`) | fait, 10:20 - 11:52 | 3080 `/root/steph-ft/g5e/a/`, `gguf/` |
| DEV 3 graines (`g5e/eval_3080.sh dev`) | fait, 11:52 - 12:15 ; a-sft regénéré : réponses identiques aux runs de G5c, verdicts A7 repris ; juge A7 de G5e, contrôles 6/6 FR et EN avant et après ; Ollama arrêté 10:20, **relancé 12:15** | 3080 `/root/steph-ft/g5e/runs/`, `verdicts/` ; `eval/g5e-eval-dev.json` |
| TEST, juge fort, formulation, Speak Bench, i5 | **non passé** : qualité EN significativement sous a-sft au DEV | scripts prêts : `eval_3080.sh test`, `useful.sh`, `style_xeon.sh`, `i5.sh`, `useful_pair.py`, `g5e_decision.py` (jamais exécutés) |

## Protocole

Recette a-sft de G5 à l'identique (`g5e/train_3080.sh` = celui de G5d sur `mix-g5e`) : `run_k3.sh`, LoRA rang 16, lr 2e-4,
3 époques, 4 graines deux à deux, soupe uniforme, GGUF Q4_K_M, depuis P17 fusionné, sur la 3080. DEV : `bench_run.py`,
harnais affiné `dev.json`, 3 graines, CUDA `9588757` ; juge A7 Qwen3.5 9B `03b74727`, 4 erreurs de juge persistantes par
run après 3 essais (exclues, comme G5) ; analyse `g5_eval.py` de G5 (python du venv), bootstrap 10 000 tirages. Runs et
verdicts de G5c repris tels quels (G5c non regénéré).

## Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| Le mélange ne change que 94 étiquettes train et 10 val, plus 276 corrections EN ajoutées | VÉRIFIÉ | `eval/mix-relabel.json` : empreintes des autres lignes égales avant et après ; assertion de `g5e_mix.py` (échouerait sur tout autre écart) ; 7 tests `test_g5e_mix.py` verts sur la 3080 | règle « nette » = `lang_v3` non indécis, sans marge ; 117 lignes de mauvaise langue gardées faute d'X4-L5 utilisable |
| Le mélange est propre | VÉRIFIÉ | `leak_check drop` 0 ligne retirée ; `scan` rejected [], 0 canari ; `audit_pii` TOTAL 0 | liste de noms du Mac du 2026-09-27 |
| La langue sous prompt EN rejoint a-sft au DEV | EXÉCUTÉ | `eval/g5e-eval-dev.json` : -0,49 [-2,71 ; +1,72] ; G5e - G5c -1,48 n.s. | un « pas d'écart » n'est pas une égalité prouvée ; DEV seul, le TEST voyait seul l'écart de G5c |
| La qualité EN reste sous a-sft | VÉRIFIÉ | -4,47 [-7,64 ; -1,30], 3 graines ; échouerait si l'IC touchait 0 | cause : non isolée (hypothèse : étiquettes `en_summary` de T9) |
| Le gain d'inventions T9 tient au DEV | VÉRIFIÉ | A7 -6,10 [-10,29 ; -1,80] ; contrôles 6/6 FR et EN avant et après | juge 9B seul ; juge fort non passé |
| a-sft rebanqué à l'identique | VÉRIFIÉ | `run.done` : IDENTIQUE a-sft dev, 3 graines | TEST non rebanqué |
| GGUF G5e | EXÉCUTÉ | `run.done` : `84cd81ee…`, 222 662 112 o ; bancs DEV rc=0 | TEST, Speak Bench, i5, formulation, juge fort non passés |
| Scripts du TEST (`eval_3080.sh test`, `useful.sh`, `style_xeon.sh`, `i5.sh`, `useful_pair.py`, `g5e_decision.py`) | ÉCRIT | - | **jamais exécutés** |
