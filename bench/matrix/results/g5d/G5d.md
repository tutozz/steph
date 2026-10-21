# G5d : G5c avec le correctif de langue de G5, pour isoler la cause du recul anglais

Dates : 2026-10-01 (mélange, entraînement, bancs DEV) et 2026-10-02 (analyse DEV, vérification des étiquettes T9).
Rien sur le Mac : seuls des agrégats (comptes, taux) en sont revenus ; le corpus n'a quitté ni la 3080 ni RTX 3060.

## Décision

**Le correctif de langue n'explique pas le recul anglais de G5c.** G5d prend le correctif de G5 et reste au niveau de
G5c sur la langue sous prompt anglais au DEV. Le TEST n'a donc pas été passé : aucune dépense OpenRouter, **a-sft reste
le modèle des PC lents**.

| DEV, 3 graines (429 cas x 2 langues) | a-sft | G5c | G5d | G5d - a-sft (IC 95 %) | G5d - G5c (IC 95 %) |
|---|---|---|---|---|---|
| Mauvaise langue, prompt EN (271 évaluations) | 4,31 % | 5,29 % | 5,41 % | +1,11 [-1,72 ; +3,94] | +0,12 [-2,71 ; +2,83] |
| Sortie FR sous prompt EN (62 évaluations) | 16,67 % | 22,58 % | 19,35 % | +2,69 [-9,14 ; +13,98] | -3,23 [-15,05 ; +7,53] |
| Qualité EN | 57,3 | 52,8 | 53,6 | **-3,70 [-6,72 ; -0,86]** | +0,87 [-1,56 ; +3,32] |
| Mauvaise langue, prompt FR | 7,87 % | 4,18 % | 5,54 % | -2,34 [-5,90 ; +1,11] | +1,35 [-1,23 ; +4,06] |
| Qualité FR | 50,1 | 53,3 | 52,4 | +2,37 [-0,83 ; +5,42] | -0,88 [-3,10 ; +1,40] |
| Qualité `score_v3` | 53,7 | 53,0 | 53,0 | -0,67 [-3,02 ; +1,69] | -0,01 [-1,78 ; +1,81] |
| Note de production (HEAD) | 78,3 | 78,1 | 78,1 | -0,21 [-1,55 ; +1,11] | +0,05 [-0,82 ; +0,94] |
| Questions présente / absente | 58,7 / 59,1 | 60,5 / 45,5 | 61,4 / 43,9 | - | - |
| Abstentions présente (/100) / absente (/40) | 3-7-5 / 12-14-13 | 6-7-7 / 11-8-11 | 3-2-2 / 9-10-10 | - | - |

Graine 7 seule (le DEV rapide prévu) : mauvaise langue EN 3,69 / 5,90 / 5,54 % (a-sft / G5c / G5d), sortie FR sous
prompt EN 16,1 / 25,8 / 19,4 %. Même lecture.

Lecture : sur la mauvaise langue EN, G5d est à G5c près (+0,12) et garde l'écart de G5c avec a-sft. La qualité EN reste
significativement sous a-sft. La sortie FR sous prompt EN baisse un peu (n.s., 62 évaluations). Le DEV ne voyait déjà
qu'un faible écart pour G5c (+0,98 n.s., contre +3,39 significatif au TEST) : il ne peut pas prouver une disparition,
mais il ne montre aucun rapprochement d'a-sft.

| Champ | Valeur |
|---|---|
| Fichier | `g5d-a-sft-Q4_K_M.gguf`, 222 662 112 o |
| sha256 | `99676e46c539fe1c5204d7d92f3a121cfe3a6672ea79e3f39987f66308ec9efc` |
| Emplacement | 3080 `/root/steph-ft/g5d/gguf/` |
| Soupe | perte val par graine 0,355 / 0,359 / 0,376 / 0,368 (graines 42, 7, 123, 2024) |
| Dépense OpenRouter | **0 $** (TEST non passé) |
| Publication | aucune ; rien de public |

## Cause probable : les étiquettes T9 elles-mêmes, mais pas comme supposé

Comptes sur RTX 3060 (machine du corpus), langue classée par `lang_v3.classify`, `final-x4-l5` (étiquettes d'a-sft)
contre `final-t9`. Aucun texte n'est sorti.

| Fichiers | Prompt | Étiquette dans l'autre langue, X4-L5 | idem, T9 |
|---|---|---|---|
| `macos.en`, `linux-low.en` (559 lignes) | EN | 8 (6 + 2) | 7 (5 + 2) |
| `macos`, `linux-low`, `linux-dev`, `snapshot-linux-dev`, `snapshot-linux-low` (3 538 lignes) | FR | 21 | **87** |
| idem, entrée en français ou neutre | FR | 9 | **65** |

- Hypothèse de départ réfutée : T9 n'écrit pas d'étiquettes françaises sous prompt anglais (7 contre 8).
- T9 écrit en revanche **4 fois plus d'étiquettes anglaises sous prompt français** (macos 3 -> 36, linux-dev 2 -> 30,
  snapshot-linux-dev 6 -> 13), presque toutes sur une entrée française ou neutre. Le lien « langue du prompt = langue de
  la sortie » s'affaiblit ; c'est le seul signal que portent les tests de langue.
- Les corrections T9 (842 lignes) sont à 83 % sous prompt FR : la part de prompts EN du mélange passe de 36,3 % (a-sft)
  à 34,2 % (G5c) et 33,5 % (G5d). Dans le mélange, les lignes « prompt FR, sortie EN » passent de 130 à 201.
- Le correctif de G5 porte moins d'exemples « prompt EN, entrée FR, sortie EN » que celui de G3b (144 contre 206) :
  G5d a moins de signal de correction que G5c, et ne fait pas pire. Le correctif n'est pas le levier.

Ces comptes sont une corrélation : aucun entraînement n'a encore isolé l'un ou l'autre mécanisme.

## Correctif proposé (G5e, non lancé)

1. Dans `final-t9`, remplacer par l'étiquette X4-L5 toute étiquette T9 dont la langue classée diffère de celle du prompt.
   Environ 66 lignes, le champ `label_source` passe à `x4`. Même règle sur `final-t9-corrections`.
2. Rééquilibrer les corrections T9 pour garder la part de prompts EN d'a-sft (36 %) : corrections EN x2, ou tirage des
   corrections FR à la même proportion.
3. Recette a-sft identique (mélange de G5d, correctif de G5), DEV 3 graines puis TEST contre a-sft si la mauvaise langue
   EN et la qualité EN rejoignent a-sft.

Les deux points se testent ensemble (un entraînement) ; en cas de succès, une ablation dira lequel porte l'effet.

## Recette et mélange

Recette a-sft de G5 à l'identique (`g5d/train_3080.sh` : `run_k3.sh`, LoRA rang 16, lr 2e-4, 3 époques, 4 graines deux à
deux, soupe uniforme, GGUF Q4_K_M, depuis P17 fusionné), sur la 3080 comme a-sft et G5c.

| Élément | G5c | G5d |
|---|---|---|
| Correctif de langue | G3b (hôte de la 3060), 125 x2 | **G5 (3080), 94 x2**, lignes identiques à celles du mélange d'a-sft |
| Contamination du correctif (`leak_check drop`) | - | 94 gardées, 0 retirée |
| Mélange train | 5 409 `9ee83dd2…` | **5 347 `18bb5c29…`** (-250 + 188, même position, ligne 4 317) |
| Mélange val | 215 `b1d7ada3…` | 215 `b1d7ada3…` (inchangé) |
| Autres lignes | - | 5 159, même ordre, empreinte `33524965…` identique avant et après |
| `audit_pii` | 0 | 0 (liste de noms copiée chmod 600, effacée) |
| `leak_check scan` | 0 cas rejeté | 0 cas rejeté, 0 ligne canari |

## État (reprise)

| Étape | État | Où |
|---|---|---|
| Mélange (`g5d/mix.sh`) | fait, 2026-10-01 20:25 | 3080 `/root/steph-ft/data/mix-g5d`, `eval/mix-sha.txt` |
| SFT, soupe, GGUF (`g5d/train_3080.sh`) | fait, 21:20 - 22:47 (carte attendue de 20:25 à 21:20, juge 9B de G3c) | 3080 `/root/steph-ft/g5d/` |
| Bancs DEV 3 graines (`g5d/eval_dev.sh`) | fait, 22:47 - 22:52 ; Ollama arrêté 21:20, relancé 22:52 | 3080 `/root/steph-ft/g5d/runs/` |
| Analyse DEV | échec le 01 (`numpy` absent du python3 de l'hôte), refaite le 02 avec le python du venv, pilote corrigé | `eval/g5d-eval-dev-3.json`, `eval/g5d-eval-dev-b7.json` |
| TEST | non passé : le recul anglais ne disparaît pas au DEV | - |
| Vérification des étiquettes T9 | faite, comptes seulement, sur RTX 3060 | ce fichier |

## Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| Le mélange de G5d ne diffère de celui de G5c que par le correctif | VÉRIFIÉ | `run.done` REMPLACEMENT : empreinte des 5 159 autres lignes identique ; assertions de `mix.sh` (échoueraient sur un autre écart) | - |
| Le correctif de G5d est celui d'a-sft | VÉRIFIÉ | comparaison des lignes `langfix_en_fr` de `mix-g5d` et `g5/mix` : égales ; sha256 `0452e923…` | - |
| Le mélange est propre | VÉRIFIÉ | `audit_pii` TOTAL 0 ; `leak_check scan` rejected [] | `audit_pii` avec la liste de noms du Mac du 2026-10-01 |
| Le recul anglais persiste dans G5d | EXÉCUTÉ | `eval/g5d-eval-dev-3.json` : mauvaise langue EN G5d - G5c +0,12 [-2,71 ; +2,83], qualité EN G5d - a-sft -3,70 [-6,72 ; -0,86] | **TEST non passé** : le DEV ne voyait déjà pas l'écart de G5c significatif ; mesure au DEV seulement |
| T9 n'écrit pas d'étiquettes FR sous prompt EN | VÉRIFIÉ | comptes RTX 3060 : 7 contre 8 sur 559 lignes | classifieur `lang_v3` : ~40 % des étiquettes classées « indécises » |
| T9 écrit 4 fois plus d'étiquettes EN sous prompt FR | VÉRIFIÉ | comptes RTX 3060 : 87 contre 21 sur 3 538 lignes | lien causal avec le recul EN : **non prouvé** |
| Le correctif G5e réduirait le recul | ÉCRIT | proposition seulement | jamais entraîné ni mesuré |
| GGUF G5d | EXÉCUTÉ | `run.done` : `99676e46…`, 222 662 112 o ; bancs DEV rc=0 | Speak Bench, i5, juges non passés |
