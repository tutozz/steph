# G3, fondation : affiner Gemma 4 E2B

Date : 2026-09-29. Aucun entraînement lourd ici : faisabilité, mesures, recette et scripts.
Aucun calcul sur le Mac : conversions, jetons, essais CPU sur la machine CPU, essai GPU sur la 3060 (carte libre à 02:30).

## Verdict

| Question | Réponse | Niveau |
|---|---|---|
| Poids d'origine | `google/gemma-4-E2B-it-qat-q4_0-unquantized` (bf16 extrait du QAT), base d'affinage retenue | VÉRIFIÉ (sha256) |
| Licence | Apache 2.0 sur les trois cartes (`license: apache-2.0`, lien `gemma_4_license`) | VÉRIFIÉ (carte lue) |
| llama.cpp b11205 | Gemma 4 supporté : conversion, quantification, LoRA GGUF à l'exécution | EXÉCUTÉ |
| Q4_0 officiel reproduit | **bit à bit** sur 540 tenseurs sur 541 depuis le bf16 QAT | VÉRIFIÉ |
| Meilleur Q4_0 que l'officiel | Q4_0 avec imatrix : KL **0,0024** contre **0,0486** pour l'officiel, même taille | VÉRIFIÉ (texte hors calibration) |
| Mémoire | LoRA bf16, plongements par couche (PLE) sur CPU : pic 7,45 Go alloués, 8,75 Go réservés (micro 4) ; 5,45 et 6,46 Go (micro 1) | EXÉCUTÉ (20 et 10 pas) |
| QLoRA 4 bits | inutile : le LoRA bf16 tient ; bitsandbytes absent des venvs des machines CPU, 3080 et 3060 | ÉCRIT (raisonnement) |
| Prompt | prompt générique de production (`SUMMARY_SYSTEM` et suivants) | EXÉCUTÉ (pertes, voir Format) |
| Scripts | `bench/matrix/finetune/gemma/`, 13 tests verts, SFT 20 pas sur la 3060, SFT et DPO 3 et 2 pas sur CPU | EXÉCUTÉ |

## 1. Poids et licence

| Dépôt HF | Fichier | Taille | sha256 (début) | Usage |
|---|---|---|---|---|
| `google/gemma-4-E2B-it-qat-q4_0-unquantized` (rév. `6befbaca`) | `model.safetensors` | 10 208 852 878 o | `33fe0cec` | **base d'affinage** |
| `google/gemma-4-E2B-it` (rév. `3e22461f`) | `model.safetensors` | 10 246 621 918 o | `2db5482b` | référence non QAT, non utilisée |
| `google/gemma-4-E2B-it-qat-q4_0-gguf` (rév. `675cff42`) | `gemma-4-E2B_q4_0-it.gguf` | 3 349 516 256 o | `fa401b55` | brut du banc X3 (`models.json`), à battre |

- Copies : machine CPU `/root/steph-ft/gemma/` (les trois), A1000 `/root/steph-ft/gemma/qat/` (base d'affinage, sha256 vérifié).
- Licence : front matter `license: apache-2.0`, `license_link: https://ai.google.dev/gemma/docs/gemma_4_license`, ligne « License: Apache 2.0 » ; O1 confirmé. Un modèle affiné redistribuable sous Apache 2.0.
- Architecture : `Gemma4ForConditionalGeneration`, 5,10 G paramètres bf16 : **PLE 2,35 G** (`embed_tokens_per_layer`, 262 144 x 8 960), couches 1,86 G, plongement principal 0,40 G (lié à `lm_head`), audio 0,31 G, vision 0,17 G. 35 couches, dont 20 partagent le cache KV (sans `k_proj` ni `v_proj`), fenêtre glissante 512, softcapping final 30.

## 2. Longueurs en jetons (gabarit Gemma 4)

`token_stats.py` sur la machine CPU, `data/final-x4` complet plus `start`, `qa_train`, `summary_residual` de `data/final` (5 602 lignes), et les harnais génériques du banc v3.

| Ensemble | n | p50 | p90 | p99 | max | > 1 536 | > 2 048 |
|---|---|---|---|---|---|---|---|
| Corpus, prompt court d'entraînement | 5 602 | 227 | 519 | 1 120 | 2 511 | 16 | 6 |
| Corpus, prompt générique de production | 5 602 | 576 | 823 | 1 354 | 2 511 | 20 | 6 |
| Réponses seules | 5 602 | 17 | 34 | 123 | 142 | 0 | 0 |
| Banc v3 dev, résumés (générique) | 768 | 779 | 1 172 | 1 431 | 1 744 | 4 | 0 |
| Banc v3 dev, questions (générique) | 90 | 450 | 1 578 | 5 439 | 5 439 | 10 | 6 |
| Banc v3 test, résumés (générique) | 1 168 | 789 | 1 197 | 1 485 | 1 635 | 7 | 0 |
| Banc v3 test, questions (générique) | 140 | 444 | 1 186 | 2 170 | 2 171 | 8 | 4 |

- **maxlen 2 048** : couvre tout le corpus sauf 6 questions (`qa_train`), coupées à gauche, jamais la réponse (`encode`, testé).
- Écart de distribution : les sorties du corpus sont coupées plus court que le plafond générique (`summary_chars` 1 500) ; résumés p50 580 jetons contre 780 au banc. Reconstruire les entrées depuis les sorties brutes au plafond générique rapprocherait le corpus de la production ; les lignes n'ont que les messages, pas la sortie brute.

## 3. Mémoire et débit

### Mesures

Essai GPU, 3060 12 Go, carte libre, torch 2.14, transformers 5.17, peft 0.21. Données : `final-x4` mélangé (graine 0), 4 970 lignes d'entraînement et 32 de validation, `--generic-prompt`, maxlen 2 048, lot 16, LoRA r16 α32 attn+mlp, lr 1e-4, points de contrôle de gradient.

| Réglage | Pas | VRAM après chargement | Pic alloué | Pic réservé | s par pas | Jetons/s (entrée + réponse) | Perte val 32 lignes |
|---|---|---|---|---|---|---|---|
| micro 4 | 20 | 4 351 Mo | **7 448 Mo** | 8 746 Mo | **12,6 à 13,0** | 695 à 724 | 0,886 -> **0,529** |
| micro 1 | 10 | 4 351 Mo | 5 452 Mo | 6 462 Mo | 12,4 à 13,3 | 691 à 729 | 0,882 -> 0,589 |

- Débit limité par le calcul, pas par le lot : micro 1 et micro 4 vont à la même vitesse. Garder micro 4, micro 2 si la carte est partagée.
- 3080 10 Go : micro 4 tient (8,75 Go réservés) sur carte libre ; plus rapide que la 3060 (non mesuré, bloquée par le disque).
- A1000 6 Go : non, même en micro 1 (6,46 Go réservés).
- RAM hôte : 17 Go disponibles au lancement sur la machine 3060, aucun échec ; le pic de RAM pendant l'essai n'a pas été relevé. Le PLE (4,7 Go) reste en mémoire CPU.

Essai CPU de fumée (machine CPU, 12 lignes, 3 pas, contention avec deux llama-server d'autres agents) : 744 s par pas, perte val 0,935 -> 0,831 ; chemin de code seulement, pas un débit.

### Pourquoi LoRA bf16 et pas QLoRA

| Composant | Paramètres | bf16 | Où |
|---|---|---|---|
| PLE `embed_tokens_per_layer` | 2,35 G | 4,7 Go | **CPU** (simple lecture par ligne, `gemma_lib.TextLM`) |
| 35 couches | 1,86 G | 3,7 Go | GPU |
| Plongement principal = `lm_head` | 0,40 G | 0,8 Go | GPU |
| Audio, vision | 0,47 G | - | supprimés au chargement |
| LoRA r16 attn+mlp | 24,2 M | 0,1 Go + Adam 0,2 Go | GPU |

- Le PLE sur CPU enlève 4,7 Go de VRAM sans rien approximer : il n'est lu que par index, jamais multiplié.
- QLoRA ne quantifierait que les couches (3,7 -> 1 Go) ; bitsandbytes ne quantifie pas les plongements. Gain 2,7 Go, inutile sur 10 et 12 Go, et il ajoute un écart d'entraînement (base NF4) à l'écart de déploiement (Q4_0).
- Les logits ne sont calculés qu'aux positions de la réponse (vocabulaire 262 144) : 17 jetons en médiane, négligeable.

## 4. Chaîne GGUF

### Mesures (machine CPU, llama.cpp b11205, KL par rapport au bf16 QAT)

Texte : docs du dépôt (`README.md`, `docs/*.md`), 40 morceaux de 512 jetons. L'imatrix a vu le début du texte ; la colonne « hors calibration » porte sur la fin, jamais vue.

| GGUF | Taille | KL moyenne | KL hors calibration | Même top-1 hors calib. | PPL/PPL bf16 hors calib. |
|---|---|---|---|---|---|
| Q4_0 officiel Google | 3 349,5 Mo | 0,0498 | **0,0486** | 90,6 % | 1,079 |
| Q4_0 reconverti sans imatrix | 3 349,5 Mo | 0,0498 | - | - | - |
| **Q4_0 avec imatrix** | 3 351,9 Mo | 0,0043 | **0,0024** | 97,9 % | 1,021 |
| Q4_K_M avec imatrix | 3 416,1 Mo | 0,0320 | 0,0273 | 92,8 % | 1,019 |
| Q3_K_M avec imatrix | 3 192,0 Mo | 0,1943 | - | - | - |
| IQ3_M avec imatrix | 3 125,6 Mo | 0,2572 | - | - | - |

- **Reproduction** : `convert_hf_to_gguf.py --outtype f16` puis `llama-quantize Q4_0` sans imatrix redonne l'officiel ; 540 tenseurs identiques octet pour octet, le 541e (`per_layer_model_proj`) ne diffère que par F16 contre BF16 (conversion faite ici en bf16).
- **Hypothèse, non vérifiée** : les poids QAT sont sur une grille Q4_0 dont l'échelle n'est pas celle de l'arrondi naïf (max absolu) ; la recherche d'échelle du chemin imatrix la retrouve. Fait mesuré : à taille égale, le Q4_0 officiel est 20 fois plus loin du bf16 QAT que le Q4_0 imatrix. Que le bf16 QAT soit meilleur que le Q4_0 officiel sur la tâche n'est pas mesuré.
- **Q3 et IQ3 ne valent rien ici** : 5 à 10 fois la KL de l'officiel pour 160 à 220 Mo de moins, parce que PLE et plongement restent en Q6_K (1,9 Go incompressibles par ces types). Pour descendre, le levier est le type du PLE (`--tensor-type per_layer_token_embd=...`), à mesurer en G4.
- Proxy seulement : la KL sur des docs ne remplace pas le banc v3. À confirmer en G4 sur le banc, y compris pour **Gemma brut requantifié Q4_0 imatrix**, candidat gratuit.

### Chaîne après affinage, exécutée

| Voie | Commande | Mesuré |
|---|---|---|
| A. Fusion puis Q4_0 imatrix | `merge_gemma.py` (soupe [+ DPO]) -> `convert_hf_to_gguf.py --outtype f16` -> `llama-imatrix` -> `llama-quantize --imatrix ... Q4_0` | essai 3060 (20 pas) : KL contre le fusionné f16 **0,0138** (imatrix) contre 0,0651 (sans), hors calibration |
| B. LoRA GGUF sur le Q4_0 officiel | `lora_gguf.py` -> `convert_lora_to_gguf.py --base <qat> --outtype f16` -> `llama-server --lora` | adaptateur de fumée 48 Mo (rang 16), chargé et appliqué : PPL 20,02 contre 20,14 sans ; base à 0,049 de KL |
| C. LoRA GGUF sur le Q4_0 imatrix du brut | même adaptateur, base `qat-Q4_0.gguf` (KL 0,0024) | écrit, jamais exécuté |

- 205 matrices = 35 couches x (q, o, gate, up, down) + 15 couches x (k, v).
- La fusion sort les poids de la grille QAT : après 20 pas seulement, l'erreur de quantification passe de 0,0024 à 0,0138 ; elle grandira avec l'entraînement complet. L'imatrix reste indispensable (5 fois moins d'erreur que sans).
- **Défaut G3 : voie A** (un seul fichier, `steph/llm.py` ne passe pas `--lora` aujourd'hui). **À trancher en G4 : A contre C**, sur le banc v3 et la vitesse i5 ; C garde la base à 0,0024 et l'adaptateur exact en f16, au prix du coût `--lora` à l'exécution (non mesuré) et d'une option à ajouter dans `llm.py`.
- Imatrix de G3 : sur le corpus steph au prompt générique, pas sur les docs (ici, docs seulement, faute d'autre texte hors corpus).

## 5. Format

### Ce que steph envoie à Gemma aujourd'hui

- Profil `generic` (`config.py` : `llm_profile = "generic"`, modèle `gemma-4-E2B_q4_0-it.gguf`).
- Résumé : `SUMMARY_SYSTEM` (15 mots, style télégraphique, règles par famille, 3 exemples de forme) + tour utilisateur `Commande / Statut / Durée / Sortie` sur `digest()` plafonné à 1 500 caractères.
- Questions (P20) : `QA_SYSTEM` + historique `Narrator.qa_messages()` au budget `qa_budget_chars` 36 000, blocs 2 500, puis `(dossier actuel : …)` et la question.
- Gabarit : `<bos><|turn>system\n…<turn|>\n<|turn>user\n…<turn|>\n<|turn>model\n` ; la réponse apprise se termine par `<turn|>`. `enable_thinking=False`, `--reasoning-budget 0` côté serveur.

### Recommandation : garder le prompt générique de production

Perte par jeton de Gemma brut (bf16 QAT, sans affinage) sur les mêmes 48 étiquettes de `final-x4`, tirées au hasard (graine 0), machine CPU, `--eval-only` :

| Prompt système | Jetons d'entrée p50 | Perte par jeton de réponse |
|---|---|---|
| court d'entraînement (`TRAIN_SYSTEM` et suivants) | 209 | 1,631 |
| **générique de production** (`SUMMARY_SYSTEM` et suivants) | 579 | **0,850** |

Les étiquettes X4 ont été écrites sous les consignes de production : le brut en est deux fois plus proche avec le prompt générique. Affiner sous le prompt court obligerait le modèle à réapprendre la forme ; sous le prompt générique, il part de ce qui a déjà donné 60,7 au banc v3.

- Le corpus a déjà les bons tours utilisateur ; seul le système change (`gemma_format.to_generic`, testé). Les questions sont déjà au `QA_SYSTEM`.
- Même harnais que le brut (`generic_harness.py`) : la comparaison G3 contre Gemma brut ne mélange pas deux changements.
- Repli immédiat : revenir au brut est un simple changement de fichier, sans changer de profil.
- Le prompt court n'économise que le préremplissage du système (environ 350 jetons), mis en cache par le slot entre deux résumés ; à rouvrir seulement si G2 montre un premier jeton limité par le préremplissage sur l'i5.

## 6. Scripts

| Fichier | Rôle |
|---|---|
| `gemma/gemma_lib.py` | chargement texte seul, PLE sur CPU, `encode` (perte sur la réponse), softcapping, clés adaptateur -> checkpoint, soupe |
| `gemma/gemma_format.py` | prompts courts d'entraînement -> prompts génériques de production |
| `gemma/train_sft_gemma.py` | copie adaptée de `train_sft.py` (non touché) : LoRA bf16, arrêt anticipé, suivi `metrics.jsonl`, `--generic-prompt`, `--max-steps` |
| `gemma/train_dpo_gemma.py` | copie adaptée de `pref/train_dpo.py` (non touché) : RPO sur la soupe SFT |
| `gemma/merge_gemma.py` | checkpoint complet fusionné (soupe moyenne + DPO ajouté) pour llama.cpp |
| `gemma/lora_gguf.py` | soupe + DPO en un seul adaptateur exact, pour `convert_lora_to_gguf.py` |
| `gemma/token_stats.py` | distribution de jetons, comptes seulement |

Tests : `test_gemma_format.py` (5), `test_gemma_lib.py` (8), 13 verts sur la machine CPU. Ce qui les ferait échouer : une table de prompts fausse, une clé d'adaptateur mal traduite (fusion silencieusement vide), un softcapping oublié, une réponse coupée par `maxlen`, une soupe mal pondérée dans `lora_gguf`.

## 7. Recette G3

| Élément | Valeur |
|---|---|
| Machine | **3060 12 Go**, `/mnt/backup-hdd/stephbench-tmp/gemma` (base déjà là, sha256 vérifié) ; 3080 si 12 Go sont libérés sur machine 3080 |
| Base | `gemma-4-E2B-it-qat-q4_0-unquantized`, bf16, texte seul, PLE sur CPU |
| Méthode | **LoRA bf16** (pas de QLoRA), r **16**, α **32**, dropout 0,05, cibles q, k, v, o, gate, up, down (205 matrices, 24,2 M paramètres) |
| Données | mélange de R2 (`compose_r1.py` sur `final-x4` + fonctionnalités de R1), **questions au format P20** (entrées régénérées par X4, pas l'ancien `qa_train`), rendu par `--generic-prompt` ; validation de R1 |
| SFT | lr **1e-4** (crible dev 5e-5, 1e-4, 2e-4 sur une graine avant les 3 graines), **2 époques**, arrêt anticipé (4 évaluations par époque, patience 3), cosinus, échauffement 3 % |
| Lot | 16 par pas, micro 4, maxlen **2 048** |
| Graines | 42, 7, 123 ; soupe uniforme des 3 adaptateurs |
| Durée estimée | environ **67 min par époque** (311 pas x 12,9 s pour 4 970 lignes), **2 h 30 par graine** évaluations comprises, 7 h 30 les trois sur la 3060 |
| DPO | **SFT seul par défaut.** Piège R2 : le DPO a fait passer l'abstention des questions à réponse présente de 12 à 33 sur 204 (dev), -18,3 pts au test. Variante seulement : `train_dpo_gemma.py` sur la soupe, paires jugées A7 **plus des paires de questions à réponse présente** (choisie : la réponse ; rejetée : « Pas dans l'historique. »), lr 1e-5, β 0,1, poids SFT 1, 60 pas, micro 2 (mémoire DPO non mesurée sur GPU), environ 40 min ; sous-groupe des questions à réponse présente mesuré à part |
| GGUF (défaut) | `merge_gemma.py --adapters s42 s7 s123 [--add dpo]` -> `convert_hf_to_gguf.py --outtype f16` -> `llama-imatrix` sur 200 lignes du corpus rendues au prompt générique -> `llama-quantize --imatrix Q4_0` ; environ 3 350 Mo |
| GGUF (contrôle) | `lora_gguf.py` -> `convert_lora_to_gguf.py` -> Q4_0 officiel + `--lora` |
| Prompt | générique de production, identique au brut (`generic_harness.py`) |
| Décision | banc v3 **test**, 3 graines, juge A7 et juge de formulation ; réglages sur dev ; doit battre le brut Q4_0 officiel (60,7) et aussi le brut requantifié Q4_0 imatrix, sur au moins un axe sans régression |

## 8. Machines

| Machine | État pour G3 | Déblocage |
|---|---|---|
| 3080 10 Go | **bloquée par le disque** : 1,2 Go libres sur `/`, il en faut 11 pour la base | libérer 12 Go (ex. `uv-cache` 7,4 Go, `ft` 8,4 Go) : décision utilisateur, rien supprimé ici |
| 3060 12 Go | **retenue** ; partagée par intermittence (juge 9B 5,7 Go, `train_kd` 4,2 Go, bancs 350M), libre à 02:30 pour l'essai ; base dans `/mnt/backup-hdd/stephbench-tmp/gemma/qat` | carte libre ; ne pas lancer si un juge 9B tourne (8,75 Go réservés + 5,7 Go > 12 Go) |
| A1000 6 Go | **exclue** : 6,46 Go réservés même en micro 1 ; base téléchargée (`/root/steph-ft/gemma/qat`), utile pour les bancs | - |
| machine CPU | conversions, imatrix, KL, fusion : 5 à 10 min chacune | - |

## 9. Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| Base = QAT non quantifié, Apache 2.0 | VÉRIFIÉ | sha256 `33fe0cec…` = oid LFS HF sur la machine CPU, A1000, machine 3060 ; carte `license: apache-2.0` | texte complet de la licence Gemma 4 non relu |
| Q4_0 officiel reproduit | VÉRIFIÉ | 540/541 tenseurs identiques octet pour octet (gguf-py, machine CPU) | le 541e diffère par le type F16/BF16 seulement |
| Q4_0 imatrix 20 fois plus proche du bf16 | VÉRIFIÉ | `logs/hkld-*.log` machine CPU, texte jamais vu par l'imatrix | proxy : aucune mesure au banc v3 ; texte de docs, pas des sorties de terminal |
| Mémoire et débit 3060 | EXÉCUTÉ | `trial-m4/train_log.json`, `trial-m1/train_log.json` (machine 3060) | 20 pas seulement ; séquences > 1 609 jetons non rencontrées ; 3080 non mesurée ; DPO sur GPU non mesuré |
| Durée 2 h 30 par graine | ÉCRIT (extrapolation) | 12,9 s x 311 pas x 2 époques + évaluations | nombre de lignes du mélange G3 inconnu tant qu'il n'est pas composé |
| Prompt générique plus proche des étiquettes | EXÉCUTÉ | `fmt-*/eval_log.json` machine CPU : 0,850 contre 1,631 sur 48 lignes | un seul tirage de 48 lignes ; perte, pas qualité au banc |
| SFT et DPO Gemma tournent | EXÉCUTÉ | fumée CPU 3 pas (perte val 0,935 -> 0,831), DPO 2 pas (marge 0 -> 0,018, précision 0,75), essai GPU 20 pas | DPO jamais lancé sur GPU ni sur de vraies paires |
| Fusion et LoRA GGUF exacts | VÉRIFIÉ | `test_gemma_lib.py` (soupe, clés, `lora_gguf` égal à soupe + DPO à 1e-5) ; GGUF fusionné et `--lora` chargés par llama.cpp | voie C jamais exécutée ; coût de `--lora` sur l'i5 non mesuré |
| Longueurs en jetons | EXÉCUTÉ | `token_stats.py` sur la machine CPU, 5 602 lignes | questions P20 régénérées par X4 non comptées (fichier non localisé) |
| Tests | VÉRIFIÉ | 13 verts sur la machine CPU ; échoueraient sur une table de prompts fausse, une clé mal traduite, un softcapping oublié, une réponse tronquée, une soupe mal pondérée | tests écrits avec le code, pas avant (TDD non respecté) |
