# G6 : MoE bruts comme modèle de base rapide des PC lents

Date : 2026-09-29. Question : un MoE à ~1B de paramètres actifs lit-il le prompt assez vite sur
l'i5-7200U pour remplacer v1.0 avec une qualité proche de Gemma 4 E2B ?

## Verdict

**Non. Aucun des 8 MoE ne passe le filtre de vitesse** (p90 des résumés dev v3 sous 8 s sur l'i5).
Le plus rapide, EuroMoE 2.6B-A0.6B, fait 8,2 s de p90 et **19,2 de qualité au test v3** contre
50,1 pour v1.0 rebanqué (-31,0 pts, IC [-33,8 ; -28,1]).

- La lecture du prompt ne suit pas les paramètres actifs : **35 à 101 jetons/s** sur l'i5, contre
  ~200 pour v1.0 et 28 pour Gemma. Un MoE à 1B actif lit comme un dense de 2 à 3B.
- Les hybrides à état récurrent (Granite 4.0 H Tiny, Ling 3.0 tiny) relisent tout le prompt à
  chaque requête : 782 à 859 jetons lus contre ~390 pour les modèles à attention. Ils sont **plus
  lents que Gemma** (p90 29,5-29,9 s contre 27,3 s).
- La RAM pic dépasse 7 Go pour 6 modèles sur 8 au réglage de production generic : inutilisable sur
  une machine de 8 Go.

## Tableau

Vitesse : i5-7200U, `-t 4`, réglages de production generic (`-c 32768 --parallel 2 -b 512 -ub 512`),
méthode G2. Résumés : 151 résumés dev v3 au format generic, un sur trois des cas `reaches_model`.

| Modèle | Total / actif | Q4 (Go) | RAM pic i5 | Lecture (j/s) | p90 i5 résumés | p90 i5 36 cas | Qualité test | Inventions | Licence |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| **v1.0** (référence, affiné) | 350M dense | 0,22 | 563 Mo | ~200 | 1,24-1,37 (prédit, R2-B1) | 2,26 | **50,1** (rebanqué) | 29,7 % (X3) | base Granite Apache-2.0 |
| Gemma 4 E2B brut (G2) | dense, 2B effectifs | 3,35 | 4,97 Go | 28 | 27,3 | 17,97 | 60,7 (X3) | 20,0 % (X3) | Apache-2.0 |
| EuroMoE 2.6B-A0.6B Instruct 2512 | 2,6B / 0,6B | 1,62 (converti) | 3,76 Go | 100,8 | **8,20** | 5,52 | **19,2** | non jugé | Apache-2.0 |
| Trinity Nano Preview | 6B / 1B | 3,79 | 8,13 Go | 54,6 | 11,03 | 7,67 | non mesurée | non jugé | OpenMDW-1.1 |
| SmallThinker 4B-A0.6B Instruct | 4B / 0,6B | 2,63 | 5,61 Go | 59,6 | 11,48 | 7,92 | non mesurée | non jugé | Apache-2.0 |
| Marco Nano Instruct | 8B / 0,6B | 5,37 (converti) | 12,84 Go | 67,2 | 10,31 | 6,96 | non mesurée | non jugé | Apache-2.0 |
| OLMoE 1B-7B 0125 Instruct | 7B / 1B | 4,21 | 12,54 Go | 41,1 | 16,76 | 11,79 | non mesurée | non jugé | Apache-2.0 |
| Granite 4.0 H Tiny (hybride Mamba) | 7B / 1B | 4,23 | 7,79 Go | 34,7 | 29,88 | 13,65 | non mesurée | non jugé | Apache-2.0 |
| Ling 3.0 tiny (hybride KDA) | 7,9B / 1,3B | 4,82 | 8,42 Go | 42,6 | 29,51 | 12,89 | non mesurée | non jugé | MIT |
| LFM2.5 8B-A1B (hybride conv.) | 8,3B / 1,5B | 5,16 | 9,19 Go | - | médiane 29,9 sur 5 cas, arrêté | 16,84 | non mesurée | non jugé | LFM Open License v1.0 (usage commercial sous 10 M$ de CA) |

Détail de vitesse (chargement, génération, médianes) : `i5/i5-table.md`.

## 1. Candidats

| Candidat | Retenu | Raison |
|---|---|---|
| Granite 4.0 H Tiny, LFM2.5 8B-A1B, OLMoE 0125, Ling 3.0 tiny, Trinity Nano, SmallThinker 4B | oui | GGUF Q4_K_M officiel (Q4_K pour SmallThinker), sha256 vérifié contre Hugging Face |
| EuroMoE 2.6B-A0.6B Instruct 2512, Marco Nano Instruct | oui | pas de GGUF officiel : `convert_hf_to_gguf.py` au tag b11205 puis `llama-quantize` Q4_K_M sur serveur Xeon |
| Qwen3.5 MoE | non | plus petite taille MoE : 35B-A3B |
| Phi-mini-MoE | non | 2,4B actifs, au-dessus de 2B |
| Nemotron Labs 3 Elastic 12B-A2B, Ling mini 2.0 | non | plus de 10B au total |
| Virtuoso 9B-A1.5B | non | aucune licence publiée |
| LLaDA-MoE 7B-A1B | non | modèle de diffusion, pas servi par `llama-server` |

Support llama.cpp b11205 : les 8 architectures chargent sur l'i5. **Ling 3.0 tiny plante sur
serveur Xeon** (`GGML_ASSERT(*cur_backend_id != -1)` à la réservation du graphe, variante CPU avec AMX)
et tourne sur l'i5.

## 2. Méthode

| Élément | Valeur |
|---|---|
| Vitesse | `i5/g6_i5.sh`, copie de `g2_run.sh` : 36 cas (`granite_ram.py`), puis 151 résumés dev v3 generic (`bench_run.py`, même `dev_sum_rm.json` que G2) ; code du banc identique octet pour octet à G2 (md5 vérifiés) |
| `--cache-ram` | 0 sur les modèles à état récurrent (Granite H Tiny, Ling, LFM2.5), défaut de production (8 192 Mo) sinon |
| Filtre | p90 des résumés > 8 s : écarté ; questions P20 prévues pour les survivants seulement |
| Discipline | une mesure à la fois ; attente d'une charge < 0,3 sans aucun `llama-server` ; deux autres chantiers (d4, G4) ont occupé l'i5 entre deux modèles, jamais pendant une mesure |
| Qualité | EuroMoE seul, hors filtre (le plus proche du seuil) ; banc v3 test, graines 7, 42 et 123, harnais X3 (`test.generic.json` sha256 `e4abce1c…`, `test.json` `a463f8bf…`), v1.0 (`45414bd2…`) rebanqué dans la même session ; CPU serveur Xeon (`systemd-run AllowedCPUs=0-31 MemoryMax=48G`, `nice -n 19`, 8 fils par couloir) ; `score_v3` et `power_v3.compare` via `x3_table.py` |
| Contrôle du rebanquage | v1.0 sur CPU serveur Xeon : 49,9 / 50,3 / 50,1 par graine, 50,1 en moyenne, contre 49,6 en X3 sous Vulkan |

## 3. Pourquoi les MoE ne lisent pas plus vite

| Constat | Mesure |
|---|---|
| La lecture du prompt coûte comme un dense bien plus gros | SmallThinker (0,6B actif) 59,6 j/s, EuroMoE (0,6B actif) 100,8 j/s, contre ~200 pour le dense 350M de v1.0 |
| Le noyau `mul_mat_id` des experts est moins efficace sur 2 cœurs AVX2 | à 1B actif, 35 à 55 j/s ; Gemma (2B effectifs, dense) 28 j/s |
| Les hybrides récurrents perdent le cache de préfixe | Granite H Tiny lit 782 jetons par résumé en médiane, Ling 859, contre 388 pour SmallThinker sur les mêmes cas : le prompt système est relu à chaque requête |
| La génération reste lente aussi | 15 à 40 jetons/s, contre 60 pour v1.0 |
| RAM | le fichier Q4 n'est qu'une partie : sans attention groupée, le cache KV à `-c 32768 --parallel 2` pèse plusieurs Go (OLMoE et Marco Nano au-delà de 12 Go) |

## 4. Qualité d'EuroMoE (hors filtre)

| | v1.0 rebanqué | EuroMoE 2.6B-A0.6B |
|---|---:|---:|
| Qualité test, 3 graines | 50,1 | **19,2** |
| Écart apparié à v1.0, IC 95 % | référence | **-30,96 [-33,79 ; -28,13]** |
| `reaches_model` | 46,7 | 19,9 |
| Questions | 47,2 | 27,5 |
| FR / EN | 49,8 / 50,4 | 21,1 / 17,2 |

- Même constat que les bruts de moins de 1B en X3 (9 à 31) : sans affinage, le prompt générique
  ne suffit pas.
- Sortie la plus fréquente, graine 7 : « failed » seul (145 fois sur 1 308). L'exemple du prompt
  système est recopié tel quel 76 fois (« Racine 685G libres sur 953G… », « Header.tsx line 42… »).
- Nettoyage de production du narrateur (`clean_runs.py`, balises `<think>`, gras) : 19,2 au lieu de
  18,3 sur la graine 7, v1.0 inchangé. Le tableau garde les sorties brutes, comme X3.
- Inventions non jugées : écart de qualité de 31 pts et filtre de vitesse raté, le juge A7 ne
  changerait pas la décision. Les deux cartes (3060, 3080) tournaient pour G3.

## 5. Recommandation pour le palier « PC lent 8 Go »

| Option | Décision |
|---|---|
| MoE brut (G6) | **écarté** : aucun sous 8 s, le seul proche du seuil perd 31 pts |
| Gemma 4 E2B brut ou affiné | écarté sur l'i5 (G2) : p90 27 s, facteur ~4 attendu de l'entrée affinée, encore ~7 s |
| **v1.0 (Granite H 350M affiné)** | **garder comme modèle du palier lent** : p90 2,26 s, 563 Mo, qualité 50 |
| Suite | le gain de qualité sur l'i5 passe par G5 (petit modèle sur le corpus 27B, puis distillation), pas par un modèle plus gros ; `steph setup` doit mesurer la vitesse de lecture (G2), pas seulement la RAM |

Piste non explorée : affiner EuroMoE (0,6B actif, Apache-2.0, 35 langues) sur le corpus 27B. Sa
vitesse i5 (8,2 s au p90 en generic) resterait 3 à 4 fois celle de v1.0, pour un gain inconnu.

## 6. Fichiers

| Fichier | Contenu |
|---|---|
| `i5/g6_i5.sh`, `i5/queue.sh` | filtre de vitesse lancé sur l'i5 (files `queue1.txt` et `queue2.txt` restées sur l'hôte : sha256 complets) |
| `i5/res/*.json`, `i5/run-log.txt`, `i5/i5-table.md` | mesures i5, sorties du modèle retirées |
| `i5_summary.py` | tableau de vitesse |
| `xeon/g6_dl.sh`, `xeon/convert.sh` | téléchargement vérifié, conversion EuroMoE et Marco Nano |
| `xeon/smoke.sh`, `xeon/lane.sh`, `xeon/lane-*.txt` | essai de fumée, couloirs du banc v3 |
| `runs/*.json`, `models.json`, `g6-table.json`, `g6-table.md` | banc v3 test, 3 graines, tableau (`x3_table.py`) |
| `clean_runs.py` | nettoyage de production des sorties (contrôle) |

Nettoyage : GGUF supprimés de l'i5 après chaque modèle ; sur serveur Xeon, poids Hugging Face et GGUF
supprimés sauf EuroMoE et la copie de v1.0 (`/root/steph-ft/g6`, 2 Go).

## Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| Aucun MoE sous 8 s au p90 des résumés i5 | VÉRIFIÉ | `i5/res/*-sum-dev.json` (`ttft_p90`), 7 modèles sur 151 cas | LFM2.5 arrêté à 5 résumés (médiane 29,9 s) ; exclu aussi par ses 36 cas (p90 16,8 s) |
| Lecture du prompt 35-101 j/s | EXÉCUTÉ, un passage par modèle | `prompt_n` et `prompt_ms` des mêmes fichiers | une seule machine de cette classe ; Q4_0 (repack AVX2) non essayé |
| Hybrides récurrents : prompt relu en entier | EXÉCUTÉ | `prompt_n` médian 782 et 859 contre 388 | `--ctx-checkpoints` non réglé |
| RAM pic 3,8 à 12,8 Go | EXÉCUTÉ | `ram_peak_mb` des 36 cas | au réglage de production seulement ; `-c 8192` non mesuré |
| EuroMoE 19,2 contre 50,1, -31,0 pts | VÉRIFIÉ | `g6-table.md`, 3 graines, bootstrap apparié | inventions non jugées ; dev non généré |
| v1.0 rebanqué cohérent avec X3 | VÉRIFIÉ | 50,1 contre 49,6 | CPU serveur Xeon contre Vulkan A1000 |
| Ling 3.0 tiny plante sur serveur Xeon | EXÉCUTÉ | `xeon/smoke.sh`, journal du serveur | cause exacte dans ggml non isolée |
| Questions P20 | non mesuré | - | aucun survivant au filtre, donc pas lancées |
