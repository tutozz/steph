# G3, affinage : Gemma 4 E2B en LoRA SFT, soupe et DPO

Date : 2026-09-29. Recette de la fondation (`FOUNDATION.md`), appliquée sur les GPU du labo. Rien sur le Mac.

JAMAIS EXÉCUTÉ : banc v3 TEST, juge de formulation, vitesse i5, DPO sur les graines 7 et 123. Ce document ne tranche pas G3 ; il livre les GGUF et un contrôle rapide sur DEV (2 graines de banc, juge A7).

## Verdict

| Question | Réponse | Niveau |
|---|---|---|
| L'affiné est-il cassé ? | **Non.** SFT graine 42 : 64,3 contre 60,3 pour le brut sur DEV, +4,0 [+2,3 ; +5,7] | EXÉCUTÉ (2 graines de banc) |
| Inventions (juge A7, reaches_model) | brut **18,6 %**, SFT 42 **12,6 %** (-6,0 [-9,2 ; -2,9]), DPO 42 **11,3 %** (-7,3 [-10,4 ; -4,2]) | EXÉCUTÉ (2 graines de banc, juge revalidé 6/6 avant et après) |
| Abstentions sur questions à réponse présente | 0 sur 68 en SFT et en DPO, aux deux graines de banc (brut : 1 et 0). Le piège R2 n'apparaît pas | EXÉCUTÉ (2 graines de banc) |
| La soupe aide-t-elle ? | **Non sur DEV** : soupe 62,7 contre 64,3 pour la graine 42 seule, écart +1,6 [+0,4 ; +2,7] en faveur de la graine seule | EXÉCUTÉ (2 graines de banc) |
| Le DPO aide-t-il ? | **Pas prouvé sur DEV** : qualité -0,3 [-1,2 ; +0,5], inventions -1,3 pt [-2,9 ; +0,3] contre le SFT 42. Tendance favorable, IC qui touche 0 | EXÉCUTÉ (2 graines de banc, 1 graine de DPO) |
| Candidats pour TEST | SFT 42 et DPO 42, Q4_0 sans imatrix ; soupe écartée | - |

## 1. Données

| Élément | Valeur |
|---|---|
| Mix | `mix-x4r1` de R3-T3 : chaîne R1 sur `data/final-x4`, sans mix-extra (qui ne quitte pas la 3080). Même mix que le concurrent Granite 4.1 3B |
| Taille | train 3 692, val 197 ; FR 1 939, EN 908 (x2), détail 306, début 272, progression 110, questions 146, flux 8, résidu 3 |
| Empreinte | train `89d793c8…`, val `f629d3b5…`, **identique à l'octet** sur la 3060 et sur la 3080 : recomposé sur chaque machine depuis son propre corpus (`build_mix.sh`), jamais copié |
| Contamination | celle de R3-T3 : `leak_check` contre v3 `0db04fa`, 0 cas dev ou test |
| Prompt | générique de production (`--generic-prompt`) : 0 ligne au prompt inconnu |
| Jetons | médiane 571, max 2 048 (coupe à gauche, jamais la réponse) |
| Questions | les 146 questions `qa_train` du mix, format historique + accusé + question, **sans** le préfixe P20 `(dossier actuel : …)`. Aucune question P20 régénérée n'a été trouvée sur les machines |

## 2. SFT

Recette : LoRA bf16 r 16, α 32, dropout 0,05, attention et MLP (205 matrices, 24,2 M paramètres), PLE sur CPU, lr 1e-4, 2 époques, cosinus, 3 % de montée, lot 16, maxlen 2 048, arrêt anticipé (4 évaluations par époque, patience 3). Crible de lr non fait : 1e-4 de la fondation.

| Graine | Machine | micro | s par pas | Durée | VRAM pic alloué / réservé | Val avant | Meilleure val | Époque |
|---|---|---|---|---|---|---|---|---|
| 42 | 3060 | 4 | 12,9 | 99 min | 8 667 / 10 286 Mo | 1,116 | **0,2314** | 2,0 |
| 7 | 3080 | 2 | 6,75 | 52 min | 6 701 / 6 860 Mo | 1,114 | **0,2310** | 1,97 |
| 123 | 3060 | 4 | 12,9 | 99 min | 8 666 / 10 336 Mo | 1,116 | **0,2395** | 1,97 |

Perte val au fil des évaluations (tous les 0,25 époque) :

| Graine | 0,25 | 0,5 | 0,75 | 1,0 | 1,25 | 1,5 | 1,75 | 2,0 |
|---|---|---|---|---|---|---|---|---|
| 42 | 0,385 | 0,308 | 0,271 | 0,250 | 0,250 | 0,240 | 0,232 | 0,231 |
| 7 | 0,376 | 0,319 | 0,286 | 0,253 | 0,238 | 0,236 | 0,232 | 0,231 |
| 123 | 0,354 | 0,284 | 0,273 | 0,254 | 0,257 | 0,245 | 0,241 | 0,240 |

- Aucune graine ne diverge ; aucun arrêt anticipé déclenché. La perte descend encore à la fin, lentement.
- Perte d'entraînement vers 0,09 à 0,12 en deuxième époque contre 0,23 en val : l'écart grandit, sans remontée de la val.
- La 3080 va **deux fois plus vite** que la 3060 (6,75 contre 12,9 s par pas).
- La base de la 3080 vit en RAM (`/dev/shm/g3-qat`, téléchargée depuis Hugging Face, sha256 `33fe0cec…` vérifié) : son disque `/` n'a que 2 Go libres.

## 3. GGUF

Chaîne (`chain.sh`, machine CPU) : `merge_gemma.py` (soupe uniforme [+ DPO]) -> `convert_hf_to_gguf.py --outtype f16` -> `llama-quantize Q4_0` **sans imatrix**, même quantification que le Q4_0 officiel QAT.

| GGUF | Taille | sha256 | Machines |
|---|---|---|---|
| `sft-s42-f16.gguf` | 9 273 527 872 o | `e77b689c477b1425a5ce9876dbc78dff392b727f2c21b55a296d01a0c3b81147` | CPU `/root/steph-ft/g3/gguf/` |
| `sft-s42-Q4_0.gguf` | 3 349 515 840 o | `93eb13e9040bcd9e4d66db5499d875678741593560d19653fc4f707bb5e10b2f` | CPU `/root/steph-ft/g3/gguf/`, A1000 `/root/steph-ft/g3/gguf/`, 3080 `/dev/shm/g3-sft-s42-Q4_0.gguf` (volatil) |
| `sft-soup-f16.gguf` (42, 7, 123) | 9 273 527 872 o | `7874d271301814bea6c04af2b070a00be9ad2f38933bdccbfcd0d553814692f0` | CPU |
| `sft-soup-Q4_0.gguf` | 3 349 515 840 o | `90c0e7163627f6ea2dba735e83117cd72fea94b2931c7980c53985626397b8be` | CPU, A1000 |
| `dpo-s42-f16.gguf` (SFT 42 + DPO 42) | 9 273 527 872 o | `61bec6b662e26191877412f2d16012f371167250392c933e5e0855377df0f346` | CPU `/root/steph-ft/g3/gguf/` |
| `dpo-s42-Q4_0.gguf` | 3 349 515 840 o | `3bb6e19c372f5380c0ad08f4a78b77a6a294ed157140bbe4880251c7d951888e` | CPU `/root/steph-ft/g3/gguf/`, A1000 `/root/steph-ft/g3/gguf/` |

Adaptateurs (sha256 de `adapter_model.safetensors`) : s42 `65ae07d1…`, s7 `d0c4621e…`, s123 `344e1ac0…`, DPO s42 `a0e1bb84…` (original sur la 3060 `…/g3/dpo/dpo-s42/adapter`, copie CPU `/root/steph-ft/g3/adapters/dpo-s42/`) ; copies dans `/root/steph-ft/g3/adapters/` (CPU et 3080), originaux sur la 3060 (`/mnt/backup-hdd/stephbench-tmp/gemma/g3/sft-s*/`) et la 3080 (`/root/steph-ft/g3/sft-s7/`).

## 4. Contrôle rapide sur DEV

A1000 Vulkan, llama b11205, harnais générique `dev.generic.json` (md5 `bba909a9`, identique à X3), `bench_run.py` au HEAD (échantillonnage de production, `--cache-ram 0`). Brut repassé dans la même session : le X3 du brut (61,1) a tourné avec l'ancien `bench_run.py`. Deux graines de banc, 42 et 7.

| Modèle | Graine de banc | Qualité | FR | EN | Résumés | Questions | Abstentions, réponse présente | Abstentions, réponse absente |
|---|---|---|---|---|---|---|---|---|
| Gemma brut Q4_0 officiel | 42 | 60,6 | 61,4 | 59,8 | 58,0 | 83,3 | 1 / 68 | 14 / 22 |
| Gemma brut Q4_0 officiel | 7 | 59,9 | 61,0 | 58,9 | 57,3 | 82,2 | 0 / 68 | 8 / 22 |
| SFT graine 42 | 42 | **64,1** | 64,3 | 64,0 | 61,8 | 83,9 | 0 / 68 | 17 / 22 |
| SFT graine 42 | 7 | **64,4** | 64,3 | 64,6 | 62,2 | 83,3 | 0 / 68 | 14 / 22 |
| SFT soupe 42, 7, 123 | 42 | 62,3 | 63,1 | 61,6 | 59,8 | 83,9 | 0 / 68 | 16 / 22 |
| SFT soupe 42, 7, 123 | 7 | 63,1 | 63,7 | 62,4 | 60,6 | 83,9 | 0 / 68 | 10 / 22 |
| DPO 42 (sur SFT 42) | 42 | 63,7 | 64,0 | 63,3 | 61,4 | 82,8 | 0 / 68 | 14 / 22 |
| DPO 42 (sur SFT 42) | 7 | 64,2 | 64,6 | 63,9 | 61,9 | 84,4 | 0 / 68 | 13 / 22 |

Juge A7 (Qwen3.5 9B Q4_K_M `03b74727…`, 2 passes, sur la 3060) sur les réponses reaches_model, cache par (harnais, cas, réponse). Contrôles plantés 6/6 FR et EN, passes A et B, avant et après chacune des deux sessions (`g3/judge/validate-*.json`).

| Modèle | Graine de banc | Invention | Douteux | Erreur | OK |
|---|---|---|---|---|---|
| brut | 42 | 99 | 47 | 4 | 392 |
| brut | 7 | 101 | 42 | 5 | 394 |
| SFT 42 | 42 | 65 | 37 | 4 | 436 |
| SFT 42 | 7 | 70 | 38 | 4 | 430 |
| DPO 42 | 42 | 59 | 46 | 4 | 433 |
| DPO 42 | 7 | 62 | 46 | 4 | 430 |

Écarts appariés par cas (`power_v3.py`, bootstrap 10 000 tirages, moyenne des 2 graines de banc) :

| Comparaison | Qualité | IC 95 % | reaches_model | Inventions (pts de % des réponses) | IC 95 % |
|---|---|---|---|---|---|
| SFT 42 - brut | **+4,0** | [+2,3 ; +5,7] | +3,0 [+0,7 ; +5,2] | **-6,0** (12,6 contre 18,6) | [-9,2 ; -2,9] |
| DPO 42 - brut | **+3,7** | [+1,9 ; +5,4] | +3,0 [+0,7 ; +5,3] | **-7,3** (11,3 contre 18,6) | [-10,4 ; -4,2] |
| DPO 42 - SFT 42 | -0,3 | [-1,2 ; +0,5] | +0,1 [-1,0 ; +1,1] | -1,3 | [-2,9 ; +0,3] |
| SFT 42 - soupe | +1,6 | [+0,4 ; +2,7] | +1,2 [-0,4 ; +2,7] | non jugé | - |

- L'IC couvre la variation entre cas ; le bruit d'échantillonnage n'est moyenné que sur 2 graines de banc.
- Douteux : brut 8,3 %, SFT 7,0 %, DPO 8,6 %. Le DPO déplace une partie des inventions vers « douteux ».
- Familles où la graine 42 gagne le plus sur le brut (graine de banc 42) : permissions +14,6, lint +9,8, réseau-transfert +9,8, processus +9,5, paquets +8,1.

## 5. DPO

Sur la 3060, avec son propre corpus (`selected.jsonl` de même sha256 `4d0b0f1b` que sur la 3080). Scripts : `g3/dpo-3060.sh`, `g3/dpo_chain-3060.sh`.

| Étape | Valeur |
|---|---|
| Politique échantillonnée | SFT 42 Q4_0, 876 entrées du mix, 4 sorties chacune (3 504), échantillonnage de production |
| Juge des sorties | A7, 2 passes, 1 873 sorties uniques en passe A, 573 en passe B ; contrôles 6/6 FR et EN avant et après |
| Verdicts des sorties | ok 2 920, invention 463, douteux 114, non jugé 7 |
| Paires (`g3_pairs.py`) | **374** : invention de résumé 231, abstention sur question à réponse présente 113, invention de question 30 ; FR 340, EN 34 ; train 338, val 36 |
| Rejeté | sortie inventée ou abstention du modèle SFT ; choisi : étiquette 27B |
| Recette | DPO + terme SFT (poids 1), LoRA r 16 sur la fusion SFT 42, lr 1e-5, β 0,1, 3 époques (66 pas), lot 16, micro 2, maxlen 2 048, prompt générique |
| Durée | 51,6 min, VRAM pic 8 161 Mo |

| Époque | Perte des paires val | Précision val | Marge val | Perte SFT val |
|---|---|---|---|---|
| 0 | 1,285 | 0,111 | 0,000 | 0,2316 |
| 1 | 1,183 | 0,861 | 0,188 | 0,2339 |
| 2 | 1,033 | 0,889 | 0,619 | 0,2420 |
| 3 | 1,006 | 0,917 | 0,739 | 0,2448 |

- La perte SFT val remonte de 0,232 à 0,245 (+5,7 %) : le prix du DPO sur la vraisemblance des étiquettes. Il ne se voit pas sur la qualité DEV (-0,3, IC qui couvre 0).
- La 3080 a aussi construit ses paires (361, même recette) ; son DPO n'a pas tourné : la carte est occupée par un juge 9B d'un autre agent.
- DPO sur une seule graine, la meilleure en SFT. Pas de soupe de DPO.

## 6. Écarts à la recette

| Écart | Pourquoi | Effet |
|---|---|---|
| Pas de crible de lr | budget GPU ; 1e-4 de la fondation | lr non optimisé |
| Questions sans le préfixe P20 | aucune entrée P20 régénérée trouvée ; les 146 questions du mix sont à l'ancien format | écart de format sur les questions, déjà relevé en R2 |
| 3080 en micro 2 | 10 Go ; même lot effectif 16 | débit par pas moins bon qu'en micro 4, mais la 3080 reste 2 fois plus rapide |
| Pas d'imatrix | consigne : même quantification que la référence QAT | la fondation mesure une imatrix 20 fois plus proche du bf16 : à passer en G4 |
| Contrôle DEV sur 2 graines de banc | temps d'A1000 | décision seulement sur TEST, 3 graines |
| DPO sur la seule graine 42 | 3080 occupée par un autre agent | pas de variance de graine pour le DPO |

## 7. Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| Trois graines SFT entraînées sans divergence | EXÉCUTÉ | `g3/sft-s*-train_log.json`, `g3/sft-s*-metrics.jsonl` | lr non criblé |
| Mix identique sur les deux GPU | VÉRIFIÉ | sha256 `89d793c8` / `f629d3b5` sur la 3060 et la 3080 | - |
| GGUF Q4_0 = Q4_0 sans imatrix, même taille que l'officiel | EXÉCUTÉ | `chain.sh`, tailles 3 349 515 840 o | KL au f16 fusionné non mesurée |
| SFT 42 meilleur que le brut sur DEV | VÉRIFIÉ | `g3/runs/*-dev-b{42,7}.json`, +4,0 [+2,3 ; +5,7] ; échouerait si l'IC couvrait 0 | TEST et juge de formulation jamais lancés |
| SFT et DPO inventent moins que le brut sur DEV | VÉRIFIÉ | `g3/judge/inv-*.json`, -6,0 et -7,3 pts, IC sous 0 ; juge 6/6 avant et après | un seul juge (9B), pas de contre-jugement 27B |
| DPO meilleur que SFT | non établi | -1,3 pt d'inventions [-2,9 ; +0,3] | TEST ; une seule graine de DPO |
| Pas d'abstention nouvelle en SFT ni en DPO | EXÉCUTÉ | 0 / 68 aux deux graines de banc | sur TEST, 3 graines |
| GGUF DPO produits | EXÉCUTÉ | `chain.sh dpo-s42 sft-s42 --add dpo-s42`, sha256 ci-dessus, copie A1000 vérifiée | KL au f16 non mesurée |
| Scripts de paires DPO | VÉRIFIÉ | `test_g3_pairs.py`, 8 tests verts sur la 3080 ; échoueraient si une abstention n'était pas rejetée sur une question à réponse présente, si une sortie égale à l'étiquette était rejetée, si une sortie douteuse faisait une paire | tests écrits avec le code, pas avant |
| Données du corpus hors du dépôt | VÉRIFIÉ | `audit_pii.py` à 0 sur tout ce qui est commité ; entrées, sorties, verdicts et paires restent sur la 3080 et la 3060, chacune depuis son propre corpus | - |
