# G3c : réaffinage de Gemma 4 E2B, recette G3b, étiquettes T9 et données publiques

Date : 2026-10-01. Rien sur le Mac (relais ssh d'adaptateurs et de GGUF seulement, aucun corpus déplacé).
Contrôle DEV d'une graine : **il vérifie que rien n'est cassé, il ne décide rien**. La décision se prend au test caché, une fois.

## Verdict

- **Rien n'est cassé, rien n'est gagné au DEV, sur les deux graines.**
  - `g3c-t9s42` : qualité 64,5 contre 65,2 pour G3b (-0,68 [-2,39 ; +1,05]), inventions A7 15,2 % contre 15,1 %.
  - `g3c-t9s7` : qualité 65,0 (-0,18 [-1,90 ; +1,50]), inventions A7 **12,6 %** (-2,42 [-5,39 ; +0,37], p 0,12).
  - Aucun écart significatif contre G3b, sur aucune mesure.
- **Le bruit d'entraînement est du même ordre que l'effet cherché.** Entre les deux graines du même mélange, les
  inventions diffèrent de -2,60 [-5,02 ; -0,19] (p 0,03). Un écart de 2 à 3 points d'inventions entre deux modèles
  d'une graine chacun ne départage donc rien.
- **Langue sous prompt anglais : signal non confirmé.** Sortie française sous prompt EN : 16,1 % pour t9s42, 12,9 % pour
  t9s7, 11,3 % pour G3b. La seconde graine revient au niveau de G3b (mauvaise langue EN 2,95 % contre 2,95 %). Le
  correctif de langue reste dilué à 4,0 % du train contre 6,4 % dans G3b.
- L'ancien mélange (x4-l5 plus public, `g3c-s42`) ne fait pas mieux : 64,0 (-1,25 [-2,93 ; +0,34]).

## Mélanges

| Mélange | Base | Ajouts | Train | Val | sha256 train / val |
|---|---|---|---:|---:|---|
| G3b (référence) | final-x4-l5, chaîne G3b | correctif de langue x2 | 3 918 | 185 | `b53e0c42…` / `a1c9c90a…` |
| G3c ancien (`g3c/mix`) | mélange G3b inchangé | publiques G3c (28,0 %) | 5 445 | 289 | `f239b37c…` / `c0146a56…` |
| **G3c-t9** (`g3c/mix-t9`) | mélange G5b : chaîne G3b sur **final-t9**, correctif x2, corrections T9 x1 (842) | publiques G3c (24,5 %) | **6 221** | 283 | `1b21fa68…` / `b0ec456a…` |

- Construction : `mix_g3c_t9.sh`, sur RTX 3060, à partir de `g5b/mix` (sha256 `94562b16…` contrôlé) et de `g3c/mix/clean/public-*`.
- Contrôles sur le tout :
  - `leak_check scan` : 0 cas rejeté sur 6 504 exemples, 0 ligne canari.
  - `audit_pii` : 0.
  - Prompts système hors de `to_generic` : 0.
- Sources du train (champ `source`) : `fr_summary` 1 861, `en_summary` 882, publiques EN 777 et FR 750, corrections
  v1.0 560, `detail` 312, corrections G3b 282, `start` 272, `langfix_en_fr` 250, `qa` 152, `progress` 108, `flux` 12,
  `summary_residual` 3.

## Entraînement

Recette G3b exacte (`train-3060.sh`, `train-t9-3060.sh`) : LoRA bf16 r16 α32, lr 1e-4, 2 époques, lot 16, micro 4,
maxlen 2048, 4 évaluations par époque, patience 3, SFT seul, `--generic-prompt`, base `gemma/qat`. 3060 RTX 3060, nice 19.

| Run | Mélange | Graine | Pas | Durée | Perte val (meilleure, époque) | Adaptateur sha256 |
|---|---|---:|---:|---:|---|---|
| `s42` | ancien | 42 | 682 | 9 021 s | 0,2703 (1,994) | `249c850e…` |
| **`t9s42`** | t9 | 42 | 778 | 10 707 s | **0,2463** (2,0) | `1406a86a…` |
| `t9s7` | t9 | 7 | 778 | 10 674 s | 0,2514 (1,995) | `a53f9327…` |

- Les pertes de validation ne se comparent pas entre mélanges, car les jeux de val diffèrent. G3b : 0,2531 sur le sien.
- `t9s42` et `t9s7` descendent jusqu'à la fin, sans arrêt anticipé. Une 3e époque n'a pas été essayée, la recette G3b fixe 2.
- `s42` a démarré avant la mise à jour T9. Son script parent a été arrêté avant s7, et il est gardé comme point de comparaison.

## GGUF

Chaîne `chain.sh` sur serveur Xeon (fusion bf16, f16, Q4_0 sans imatrix, off-ple3 `per_layer_token_embd=q3_k`). Elle reproduit
G3b tenseur pour tenseur sur l'adaptateur G3b (541/541). Emplacement : serveur Xeon `/root/steph-ft/g3c/ft/gguf/`. Copie du
Q4_0 sur la 3080 : `/dev/shm/g3c/<nom>.gguf`, sha256 identique à l'arrivée.

| Fichier | Octets | sha256 |
|---|---:|---|
| `g3c-t9s42-f16.gguf` | 9 273 527 872 | `42d210d5a7ab96dfe6ee1bf452e2a0c14328656571064165b3d2779b740d47cc` |
| `g3c-t9s42-Q4_0.gguf` | 3 349 515 840 | `ea1dcaef5740915fc4e4127ebe0927b9bc455a055f8aaadd9e3da61499980759` |
| **`g3c-t9s42-off-ple3.gguf`** | 2 432 011 840 | `14de883552d2a688325ad5c86e58cced79345fb9aa0214cc013c5a498f685880` |
| `g3c-t9s7-f16.gguf` | 9 273 527 872 | `da02ec695da360af9a17eed82435e6f596db39b1abbb13339e0ec25801155844` |
| `g3c-t9s7-Q4_0.gguf` | 3 349 515 840 | `380aaf03702144237a929c28046bec7b70b47f5643bd29dfa5564588c685c6a2` |
| **`g3c-t9s7-off-ple3.gguf`** | 2 432 011 840 | `3e36aeed1503032fbd831b40a70359d9770c4dd87543a7c71d9c0df7f7c7f76b` |
| `g3c-s42-f16.gguf` | 9 273 527 872 | `db394cc447337c2cef6c0542a2a004131bebed0472550cf2e9732edcec5c8522` |
| `g3c-s42-Q4_0.gguf` | 3 349 515 840 | `8f08a20fa6ad0731ab425ebd9de5b431b2abe2898045775fb60e87ed73569286` |
| `g3c-s42-off-ple3.gguf` | 2 432 011 840 | `e70012d44a9730520c0a88829ea0b448fab8afbea530b25098159e1f39aad6cd` |

## Contrôle DEV

Protocole :

- Banc v3 dev générique aligné L5 (`e96d54d4`, 858 évaluations), graine de banc 42.
- 3080, llama.cpp de G3b, `dev-3080.sh` ; juge A7 Qwen3.5 9B `03b74727`, contrôles 6/6 FR et EN avant et après.
- Mesures : `dev_eval.py`, avec la méthode de `g3b_eval.py` (écarts appariés par cas, bootstrap 10 000).

| Modèle | Qualité | FR / EN | Production (modèle) | Questions (présente) | Inventions A7 | Douteux | Mauvaise langue FR / EN | Sortie FR sous prompt EN |
|---|---:|---|---|---:|---:|---:|---|---:|
| G3b | 65,2 | 66,7 / 63,7 | 82,7 (71,0) | 81,7 (84,6) | 15,1 % | 6,5 % | 6,27 / 2,95 % | 11,3 % |
| g3c-s42 (ancien) | 64,0 | 65,6 / 62,3 | 82,4 (69,8) | 81,7 (84,6) | 15,2 % | 6,1 % | 6,64 / 3,69 % | 14,5 % |
| **g3c-t9s42** | 64,5 | 66,1 / 63,0 | 82,2 (69,4) | 82,8 (86,0) | 15,2 % | 7,1 % | 5,17 / 4,43 % | 16,1 % |
| **g3c-t9s7** | 65,0 | 66,1 / 64,0 | 82,5 (70,2) | 84,4 (88,2) | 12,6 % | 7,1 % | 4,80 / 2,95 % | 12,9 % |

| Écart | g3c-s42 contre G3b | g3c-t9s42 contre G3b | g3c-t9s7 contre G3b | **t9s7 contre t9s42 (bruit)** |
|---|---|---|---|---|
| Qualité | -1,25 [-2,93 ; +0,34] | -0,68 [-2,39 ; +1,05] | -0,18 [-1,90 ; +1,50] | +0,51 [-0,84 ; +1,90] |
| Production | -0,33 [-1,19 ; +0,51] | -0,44 [-1,24 ; +0,36] | -0,21 [-1,15 ; +0,72] | +0,23 [-0,54 ; +1,01] |
| Inventions A7 | +0,19 [-3,35 ; +3,72] | +0,19 [-3,16 ; +3,53] | -2,42 [-5,39 ; +0,37] | **-2,60 [-5,02 ; -0,19]**, p 0,03 |
| Questions, réponse présente | 0,0 [-4,41 ; +4,41] | +1,47 [-3,68 ; +7,35] | +3,68 [-2,21 ; +9,56] | +2,21 [-4,41 ; +8,82] |
| Mauvaise langue, prompt EN | +0,74 [-1,11 ; +2,58] | +1,48 [-1,11 ; +4,06] | 0,0 [-2,21 ; +2,21] | -1,48 [-3,69 ; +0,37] |

- `dev-eval.json` (3080, `/root/steph-ft/g3c/ft/`) : relancé avec t9s7, il redonne à l'identique les lignes déjà publiées
  pour G3b, s42 et t9s42. `dev-eval-seeds.json` : t9s7 apparié à t9s42.
- Le `dev_eval.py` de la 3080 se lance avec `/root/steph-ft/venv/bin/python` et
  `PYTHONPATH=repo/bench/matrix/v3/tools:repo2/bench/matrix/results/finetune/loop/round-3/r3t2p3:repo2/bench/matrix/finetune:repo/src`
  (le `lang_v3` de r2c1 a une autre signature).

Inventions jugées : 538 réponses `reaches_model` par modèle (4 erreurs du juge).

## Niveau de preuve

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| Mélange t9 sans fuite ni PII | VÉRIFIÉ | RTX 3060 `g3c/mix-t9/leak.log` (`rejected: []`), `pii.log` (TOTAL 0) ; `train-t9-3060.sh` refuse de démarrer sinon | contrôle par empreintes, pas sémantique |
| SFT t9s42 et t9s7 recette G3b | EXÉCUTÉ | `g3c/train/run.done` (rc=0 pour les deux), `logs/sft-t9s*.log` | deux graines seulement |
| GGUF t9s42 et t9s7 conformes | VÉRIFIÉ | sha256 serveur Xeon = 3080 (`finish.sh` s'arrête sinon) ; chaîne identique à G3b tenseur pour tenseur sur l'adaptateur G3b | off-ple3 jamais exécuté au banc (seul le Q4_0 l'a été) |
| Rien n'est cassé au DEV | VÉRIFIÉ | `dev-eval.json` (3080) : aucun écart significatif sur les deux graines, contrôles du juge 6/6 avant et après | une graine de banc ; juge 9B seul, sans contre-jugement 27B |
| Bruit d'entraînement mesuré | EXÉCUTÉ | `dev-eval-seeds.json` : inventions -2,60 [-5,02 ; -0,19] entre graines | deux graines ne donnent pas la variance, seulement un écart |
| s42 ancien terminé sans erreur | EXÉCUTÉ | adaptateur présent et dernière ligne du journal | son code de retour n'a pas été lu (script parent arrêté), la note `rc=0` vient du fichier |

## Reste à faire

- Test caché, une seule fois, contre G3b : à décider. Le DEV ne montre aucun gain à confirmer ; choisir la graine au DEV
  (t9s7 a moins d'inventions) serait un réglage sur DEV, légitime, mais l'écart est dans le bruit d'entraînement.
- Piste si l'on continue : remettre le correctif de langue à sa part G3b (x3), et régler la dose publique sur le DEV.
