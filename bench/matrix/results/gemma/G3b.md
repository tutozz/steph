# G3b : Gemma 4 E2B réaffiné avec le bloc L5 et un correctif de langue

Date : 2026-09-29 et 30. Rien sur le Mac (relais de petits fichiers et flux ssh seulement).

## Décision

**G3b est adopté** (règle T5 tenue contre le brut) : GGUF **`g3b-Q4_0.gguf`**, 3 349 515 840 o, sha256 **`e7ca421b0640d2aea4334f3273064d01c0a4764d8b6390ad434be6480a13ae74`** (serveur Xeon `/root/steph-ft/g3b/gguf/`, 3080 `/dev/shm/g3b-Q4_0.gguf` volatil). f16 : `810f0b9d093a6a3c910ffaf9747d754f3d9183f843aa732a2d8ff5058e795ccc`.

| Règle T5, G3b contre brut | Écart, IC 95 % | Verdict |
|---|---|---|
| Qualité non inférieure | **+3,45 [+1,98 ; +4,91]** | meilleur |
| Meilleur sur au moins un axe | qualité, note de production **+1,18 [+0,07 ; +2,31]**, questions **+2,74 [+0,71 ; +5,36]**, formulation **+27,5 [+19,2 ; +35,8]** | oui |
| Aucune régression significative | inventions -0,52 [-3,19 ; +2,02] ; mauvaise langue EN +0,24 [-0,97 ; +1,45], FR -1,37 [-3,47 ; +0,65], sortie FR sous prompt EN -0,68 [-5,10 ; +3,74] ; abstentions sur réponse présente 1 / 2 / 2 contre 1 / 1 / 2 | aucune |
| Verdict | | **tenu** |

- **Le correctif de langue marche** : contre G3 SFT 42 rejoué sur l'entrée L5, mauvaise langue EN **-1,61 [-3,31 ; -0,08]**, sous-groupe sortie FR sous prompt EN **-6,46 [-12,93 ; -0,68]** (9,9 % contre 16,3 %). G3 SFT 42 garde sa régression sur ce banc : +1,86 [+0,24 ; +3,71] contre le brut.
- **Le gain d'inventions de G3 ne se retrouve pas** : G3b 17,6 % contre 18,2 % pour le brut (écart non significatif) ; G3 SFT 42 16,0 % (-2,22 [-4,64 ; +0,28], non significatif sur ce banc, significatif en G3 sur l'ancien harnais). Tendance G3b contre G3 : +1,69 [-0,36 ; +3,75].
- G3b ne se distingue pas de G3 SFT 42 en qualité (-0,63 [-1,81 ; +0,55]), en note de production (+0,01) ni en formulation (-4,6 [-13,3 ; +4,6] ; FR -11,4 [-23,8 ; +1,9]).
- Vitesse et RAM non remesurées : même architecture et même taille que le brut (G2 : trop lent sur l'i5). Les variantes quantifiées de G4 portent sur le brut, pas sur G3b.

## Tableau (banc v3 test aligné L5, 3 graines, même session 3080)

Harnais générique L5 `8d90a662` pour les Gemma, affiné L5 `705fdcb9` pour v1.0. Note de production : `score_production.py` (aides D5, garde-fou d'ancrage, harnais du run). Inventions : juge A7, réponses `reaches_model`, 3 graines. Mauvaise langue : `lang_v3` sur les évaluations `reaches_model` ; sous-groupe : cas à sortie française (`output_lang` fr) sous prompt anglais, 98 évaluations.

| Modèle | Qualité | Note de production | Questions (présente) | Inventions | Douteux | Mauvaise langue FR / EN | Sortie FR sous prompt EN | Abstentions présente / absente |
|---|---|---|---|---|---|---|---|---|
| Gemma 4 E2B brut QAT q4_0 (`fa401b55`) | 60,6 | 67,6 | 85,7 (86,7) | 18,2 % | 8,2 % | 6,30 / **2,74** % | 10,5 % | 1-1-2 / 20-29-30 |
| G3 SFT 42 (`93eb13e9`, entraîné sans L5) | **64,6** | 68,7 | **89,1** (90,0) | **16,0 %** | 5,9 % | 5,81 / 4,60 % | 16,3 % | 1-2-2 / 33-35-35 |
| **G3b** (`e7ca421b`) | 64,0 | **68,8** | 88,5 (**90,2**) | 17,6 % | **5,8 %** | **4,92** / 2,99 % | **9,9 %** | 1-2-2 / 35-32-32 |
| steph-speak v1.0 (`45414bd2`) | 50,6 | 58,9 | 46,9 (47,0) | 29,5 % | 10,1 % | 8,96 / 12,27 % | 39,5 % | 8-9-9 / 19-19-18 |

- Qualité par graine : brut 59,9 / 61,2 / 60,6 ; G3 64,5 / 64,8 / 64,6 ; G3b 63,6 / 64,2 / 64,2 ; v1.0 50,6 / 50,5 / 50,8. Part dite en code : 40,5 % pour tous.
- Formulation à l'oral (juge 27B, graine 7, 240 paires) : G3b contre brut **94 contre 28**, 118 égalités (91 instables), net **+27,5 [+19,2 ; +35,8]** (FR +25,7, EN +28,9) ; G3b contre G3 SFT 42 : 54 contre 65, net -4,6 [-13,3 ; +4,6].
- Pour mémoire, G3 sur l'ancien harnais (G3-eval) : brut 60,5, SFT 42 63,4, mauvaise langue EN 3,6 et 5,8 %.

## Écarts appariés

Bootstrap apparié par cas, 10 000 tirages (`power_v3`), `g3b/eval/g3b-eval.json`.

| Axe | G3b - brut | G3b - G3 SFT 42 | G3 SFT 42 - brut | G3b - v1.0 |
|---|---|---|---|---|
| Qualité | **+3,45 [+1,98 ; +4,91]** | -0,63 [-1,81 ; +0,55] | **+4,07 [+2,71 ; +5,45]** | **+13,37** |
| Note de production | **+1,18 [+0,07 ; +2,31]** | +0,01 [-0,86 ; +0,89] | **+1,16 [+0,08 ; +2,28]** | **+9,87** |
| reaches_model | **+3,16 [+1,32 ; +5,09]** | -0,29 | **+3,45** | **+14,83** |
| Résumés | **+3,53 [+1,94 ; +5,11]** | -0,63 | **+4,16** | **+9,99** |
| Questions | **+2,74 [+0,71 ; +5,36]** | -0,60 | **+3,33** | **+41,55** |
| Questions, réponse présente | **+3,50 [+0,83 ; +7,00]** | +0,17 | **+3,33** | **+43,17** |
| Inventions, 3 graines | -0,52 [-3,19 ; +2,02] | +1,69 [-0,36 ; +3,75] | -2,22 [-4,64 ; +0,28] | **-11,74** |
| Mauvaise langue, prompt FR | -1,37 [-3,47 ; +0,65] | -0,89 [-2,10 ; +0,24] | -0,48 | **-4,04** |
| Mauvaise langue, prompt EN | +0,24 [-0,97 ; +1,45] | **-1,61 [-3,31 ; -0,08]** | **+1,86 [+0,24 ; +3,71]** | **-9,28** |
| Sortie FR sous prompt EN | -0,68 [-5,10 ; +3,74] | **-6,46 [-12,93 ; -0,68]** | +5,78 [-0,34 ; +12,24] | **-29,59** |
| Formulation, net | **+27,5 [+19,2 ; +35,8]** | -4,6 [-13,3 ; +4,6] | - | - |

## Données

| Élément | Valeur |
|---|---|
| Recette | `gemma-4-E2B-it-qat-q4_0-unquantized`, LoRA bf16 r 16, α 32, attention et MLP, lr 1e-4, 2 époques, lot 16, micro 4, maxlen 2 048, graine 42, prompt générique : recette G3 inchangée, sans DPO |
| Mix G3 sur `final-x4-l5` | chaîne R3-T3 (`compose_train`, `compose_k3 --max-chars 587`, `compose_r1 --repeat en_summary=2 --keep detail=0.5`) : train 3 840, val 196 (G3 : 3 692 et 197) ; `lost_fact` FR 259 -> 181, le bloc L5 porte des faits que le filtre ne voyait pas |
| Contamination | empreintes v3 au HEAD (`leak_check.py prints`, entrées L5) : **le mix de G3 lui-même fait rejeter 8 cas** que le contrôle de G3 (`0db04fa`) ne voyait pas ; le mix L5 en fait rejeter 18, le correctif 6. Filtre par ligne (`leak_check.py drop`, nouveau) : train -172, val -11, correctif -1 ; mix final 0 cas rejeté, 0 ligne canari |
| Correctif de langue | 3 544 enregistrements bruts FR, 462 à sortie française (`lang_v3` : 3 mots-outils français au moins, plus que d'anglais), **281 uniques** ; entrée `label.build_messages(rec, 587, "en")` (prompt anglais de production, bloc L5, sortie française) ; enseignant Qwen3.5 9B (`03b74727`) sur la 3060 |
| Consigne de l'enseignant | sans consigne, **116 étiquettes sur 281 en français** (passe abandonnée, `work/pass1/`) ; avec `EN_NOTE` lue par l'enseignant seul (« Always answer in English, even when the command output is in French. ») : 178 anglaises, 77 françaises, 26 indéterminées ; la ligne d'entraînement garde `TRAIN_SYSTEM_EN` |
| Juge A7 du correctif | 2 passes, ok 126, invention 50 (48 « ligne »), douteux 2 ; seules les `ok` gardées ; contrôles 6/6 FR et EN avant et après |
| **Dose** | **125 lignes x 2 = 250 exemples, 6,4 % du train** (x2 comme les résumés anglais du mix) |
| Mix final | train **3 918**, val 185 ; sha256 train `b53e0c42…`, val `a1c9c90a…`, correctif `a42d1e3c…` (`g3b/mix-counts.txt`) |
| SFT | 3060, 20:30 à 22:19, 12,8 s par pas, 490 pas, pic 8 667 Mo ; val 1,104 -> 0,287 (époque 1) -> **0,2531** (1,99), sans arrêt anticipé ; adaptateur `ae25437a…` |
| GGUF | `chain.sh` (serveur Xeon) : fusion bf16, `convert_hf_to_gguf.py --outtype f16`, `llama-quantize Q4_0` **sans imatrix**, comme le Q4_0 QAT officiel |

## Protocole

| Élément | Valeur |
|---|---|
| Générations | 3080 CUDA, llama.cpp `9588757` (celui de G3), `bench_run.py` au HEAD (échantillonnage de production, `--cache-ram 0`), `-ngl 99`, 2 couloirs, 12 runs, 0 réponse manquante |
| Juge A7 | Qwen3.5 9B Q4_K_M `03b74727`, `judge_lib` A7 intact, `judge_x3.py`, 2 passes, cache par (contexte, réponse) propre à G3b ; brut et G3 sur la 3060, G3b et v1.0 sur la 3080 ; contrôles 6/6 FR et EN avant et après sur chaque carte |
| Juge de formulation | Qwen3.5 27B Q4_K_M `84b5f7f1`, serveur Xeon CPU, cœurs 0-31, nice 19 ; **un slot et `--cache-ram 0`** ; revalidé : 57/60 contrôles plantés, 20/20 égalités, biais de position 48,7 % (G3 : 57/60, 48,7 %) |
| Statistiques | `g3b/g3b_eval.py` (de `g3_eval.py`, plus la note de production et le sous-groupe de langue) ; chiffres seuls dans `g3b/eval/g3b-eval.json` |
| Hors dépôt | sorties, verdicts, mix : 3080 `/root/steph-ft/g3b/`, 3060 `/mnt/backup-hdd/stephbench-tmp/gemma/g3b/`, serveur Xeon `/root/steph-ft/g3b/` |

Sha256 des runs (16 premiers) : brut `69e5d4ce` `eb273a20` `952c4eb3` ; G3 `f0b57222` `e2494b22` `2f026632` ; G3b `72fc113c` `cb7acc00` `84c0d411` ; v1.0 `6767e036` `ba7cd256` `d63dd82d` (graines 7, 42, 123).

## Écarts et incidents

| Écart | Effet |
|---|---|
| A1000 injoignable à 17:18 (ARP en échec depuis serveur Xeon) pendant le premier run | tout le banc repris sur la 3080 ; le couloir de l'A1000 n'a pas été arrêté (machine hors réseau) : **à arrêter par son PID si elle revient**, ses runs ne comptent pas |
| Juge 9B de G4 sur la 3060 de 17:10 à 20:30 | SFT retardé de 3 h 20 ; attente de la carte ramenée à 5 s |
| Juge de formulation en CPU avec `--parallel 2` : 4 contrôles sur 60, biais 86,6 % | arrêté avant toute paire ; un slot et `--cache-ram 0` rendent 57/60 (`g3b/eval/style-controls-*.json`) |
| Enseignant 9B en français 116 fois sur 281 sous prompt anglais | consigne réservée à l'enseignant ; le biais de G3 vient peut-être aussi d'étiquettes EN du corpus |
| Dose du correctif sous « quelques centaines » | vivier : 281 sorties françaises uniques dans le corpus ; 125 lignes gardées, répétées 2 fois |
| Mix de base différent de G3 (+148 lignes avant filtre, -172 après) | G3b et G3 diffèrent par L5, le filtre de contamination et le correctif : l'effet du seul correctif n'est pas isolé |
| Ollama de la 3080 arrêté par G4 puis par G3b (22:39 à 23:33) | relancé à 23:33 par `judge-3080.sh` |
| Une seule graine d'entraînement | pas de variance d'entraînement |

## Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| G3b meilleur que le brut en qualité et en note de production | VÉRIFIÉ | `g3b-eval.json`, IC au-dessus de 0, 3 graines ; échouerait si l'IC couvrait 0 | une seule graine d'entraînement |
| Mauvaise langue EN corrigée | VÉRIFIÉ | G3b - G3 : -1,61 [-3,31 ; -0,08], sous-groupe -6,46 [-12,93 ; -0,68] ; G3b - brut +0,24 n.s. | sous-groupe de 98 évaluations, IC large ; borne haute de G3b - G3 à -0,08 |
| Aucune régression d'inventions contre le brut | VÉRIFIÉ | -0,52 [-3,19 ; +2,02] ; contrôles A7 6/6 avant et après, deux cartes | un seul juge (9B) ; juges répartis sur deux cartes |
| Formulation préférée au brut | VÉRIFIÉ | +27,5 [+19,2 ; +35,8], 240 paires, juge revalidé 57/60 | une graine de banc (7) |
| Mix sans fuite | VÉRIFIÉ | `leak_check.py scan` : 0 cas rejeté sur 4 103 exemples ; test `drop` vert | seuils de v3-fp1, pas de contrôle sémantique |
| `g3b_langfix.py`, `leak_check.py drop` | VÉRIFIÉ | 9 et 5 tests verts sur la 3060 ; échoueraient si une étiquette française passait, si un verdict douteux était gardé, si la consigne entrait dans la ligne d'entraînement, si une ligne contaminée restait | tests de `g3b_langfix` écrits avec le code (sauf celui de la consigne, rouge d'abord) |
| GGUF Q4_0 livré intact | VÉRIFIÉ | sha256 serveur Xeon = sha256 3080 = `e7ca421b…` | KL au f16 non mesurée |
| Vitesse et RAM de G3b | JAMAIS EXÉCUTÉ | - | même taille que le brut, non remesuré |
| Formulation entendue en synthèse vocale | JAMAIS EXÉCUTÉ | - | personne n'a écouté |
