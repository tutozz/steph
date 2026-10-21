# G4b : la variante `off-ple3` sur le Gemma affiné G3b

Date : 2026-09-30. Rien sur le Mac (flux ssh de fichiers seulement).

## Décision

**`off-ple3` s'applique à G3b sans perte significative.** Trois axes, tous à IC couvrant 0 (critère tenu).

| Champ | Valeur |
|---|---|
| Fichier | `g3b-off-ple3.gguf`, 2 432 011 840 o (**2,43 Go** contre 3,35 pour le Q4_0 de G3b) |
| sha256 | `eb6e76076b819d9e7a1bbb01e38e8cbf256eb3bd741b6cb0c6311a4a7ed3b429` |
| Chemin | serveur Xeon `/root/steph-ft/g3b/g4b/g3b-off-ple3.gguf` ; copie i5 `/root/g4b/gguf/off-ple3.gguf` ; 3080 `/dev/shm/g4b/` (volatil) |
| Recette | `llama-quantize --tensor-type per_layer_token_embd=q3_k g3b-f16.gguf <sortie> Q4_0` (b11205, sans imatrix), `g4b/quant.sh` |
| Source | f16 de G3b `810f0b9d093a6a3c910ffaf9747d754f3d9183f843aa732a2d8ff5058e795ccc` |
| Référence | `g3b-Q4_0.gguf`, sha256 `e7ca421b0640d2aea4334f3273064d01c0a4764d8b6390ad434be6480a13ae74`, 3 349 515 840 o |

- **Couches identiques à G3b Q4_0** : 540 tenseurs sur 541 égaux (type et md5 des données) ; seul `per_layer_token_embd.weight` passe de Q6_K à Q3_K (`gguf-py` b11205, script inline, sortie dans ce compte rendu).
- Écart de taille avec G4 (`b47196ac…`, 2 432 012 256 o) : autre modèle, autre sha ; même recette, même taille à 416 o près (métadonnées).

## Q4_0 contre `off-ple3` (banc v3 test aligné L5, 3 graines, même session)

Harnais générique L5 `8d90a662` (celui de G3b pour les Gemma). Écarts appariés par cas, bootstrap 10 000 tirages (`power_v3`, méthode de G3b). Inventions : juge A7 9B, réponses `reaches_model`, 2 477 verdicts par modèle. Ligne du haut : G3b Q4_0 ; dessous : `off-ple3`.

| Axe | G3b Q4_0 | `off-ple3` | Écart `off-ple3` - Q4_0, IC 95 % | Verdict |
|---|---|---|---|---|
| Qualité `score_v3` | 64,0 | 63,7 | -0,37 [-1,11 ; +0,38] | n.s. |
| Note de production (`score_production.py`) | 68,8 | 68,8 | 0,00 [-0,56 ; +0,59] | n.s. |
| Inventions A7 | 18,0 % | 19,1 % | +1,07 [-0,36 ; +2,54] | n.s. |
| Douteux A7 | 6,3 % | 6,8 % | - | - |
| Résumés | 61,1 | 60,7 | -0,42 [-1,23 ; +0,37] | n.s. |
| Questions | 88,5 | 88,6 | +0,12 [-1,43 ; +1,67] | n.s. |
| Questions, réponse présente | 90,2 | 90,0 | -0,17 [-2,17 ; +1,83] | n.s. |
| Questions, réponse absente | 84,2 | 85,0 | +0,83 [0,00 ; +2,50] | n.s. (borne à 0) |
| `reaches_model` | 62,3 | 61,9 | -0,34 [-1,28 ; +0,60] | n.s. |
| FR / EN | 64,4 / 63,6 | 63,9 / 63,4 | -0,57 [-1,51 ; +0,32] / -0,16 [-1,24 ; +0,97] | n.s. |
| Mauvaise langue, prompt FR | 4,92 % | 5,00 % | +0,08 [-0,65 ; +0,81] | n.s. |
| Mauvaise langue, prompt EN | 2,99 % | 2,58 % | -0,40 [-1,29 ; +0,48] | n.s. |
| Sortie FR sous prompt EN (98 évaluations) | 9,9 % | 8,8 % | -1,02 [-4,42 ; +2,72] | n.s. |
| Abstentions, réponse présente (3 graines) | 1 / 2 / 2 | 1 / 2 / 2 | - | identique |
| Abstentions, réponse absente | 35 / 32 / 32 | 29 / 34 / 35 | - | - |
| Qualité par graine 7 / 42 / 123 | 63,6 / 64,2 / 64,2 | 63,0 / 63,9 / 64,1 | - | - |

- **Tendance à surveiller : inventions +1,07**, IC [-0,36 ; +2,54], sans significativité ; les replis de garde-fou sur résumé entièrement écarté montent de 19 / 18 / 19 à 27 / 24 / 21 par graine, sans effet sur la note de production (0,00). Dans G4 sur le brut : +0,28 [-1,37 ; +1,90]. La puissance du banc ne permet pas d'exclure un point d'inventions.
- **Reproductibilité** : G3b Q4_0 regénéré dans cette session (`bench_run.py`, llama.cpp `9588757`, 3080 CUDA) redonne **3 924 réponses sur 3 924 identiques** aux runs de G3b (3 graines x 1 308).
- Formulation à l'oral (juge 27B) non repassée, comme en G4.

## Vitesse et RAM sur l'i5

i5-7200U, `llama-server` b11205, réglages de production generic de G2 et G4 (`-c 32768 --parallel 2 -b 512 -ub 512 -ngl 0 -t 4`, `--cache-ram 8192`), 51 résumés dev v3 `reaches_model` (`sum50.json` de G4), machine libre (charge < 0,3, aucun `llama-server` ni `piper`), une mesure à la fois, **deux passes par modèle** (Q4_0, off-ple3, off-ple3, Q4_0), `g4b/i5.sh`.

| Modèle | RAM pic `llama-server` (passes a / b) | 1er jeton médiane | 1er jeton p90 | max | Génération | Chargement |
|---|---|---|---|---|---|---|
| G3b Q4_0 | 4 775 / 4 768 Mo | 13,57 / 13,73 s | **27,03 / 27,22 s** | 40,8 / 41,5 s | 11,0 / 10,9 j/s | 3,1 s |
| G3b `off-ple3` | **3 892 / 3 895 Mo** | 13,55 / 13,79 s | **27,08 / 27,30 s** | 40,9 / 41,4 s | 11,0 / 11,0 j/s | 3,0 s |
| Écart | **-879 Mo** (moyenne des deux passes) | 0,0 s | +0,07 s | - | 0 | - |

- **La RAM baisse comme en G4** : -881 Mo sur le brut, -879 Mo sur G3b. Le premier jeton ne bouge pas (l'écart est sous la variation entre passes du même modèle, 0,2 s).
- **RAM totale steph : environ 4,1 Go** (3 894 Mo plus 208-224 Mo de steph et Piper, mesure Q1 reprise de G4, non remesurée).
- L'i5 reste trop lent pour Gemma (p90 27 s) : conclusion de G2 inchangée.
- Chargement 3 s : GGUF chauds (copiés avant la mesure, machine sans autre charge), contre 7 à 10 s en G4.

## Protocole

| Élément | Valeur |
|---|---|
| Quantification | serveur Xeon CPU, `systemd-run -p AllowedCPUs=0-31 -p MemoryMax=32G`, `nice -n 19`, b11205 ; 20 s de calcul, pic 7,9 Go |
| Transfert | flux ssh serveur Xeon vers 3080 (`/dev/shm/g4b/`) et vers i5 ; sha256 vérifiés après copie : `e7ca421b…` et `eb6e7607…` sur les deux machines |
| Générations | 3080 CUDA, llama.cpp `9588757`, `bench_run.py` de G3b (échantillonnage de production, `--cache-ram 0`), `-ngl 99`, graines 7, 42, 123, 6 runs, 0 réponse manquante, `g4b/lane.sh` ; juges `g4b/judge.sh` (3080) et `g4b/judge-3060.sh` |
| Juge A7 | Qwen3.5 9B Q4_K_M `03b74727…`, `judge_lib` A7 et `judge_x3.py` de G3, 2 passes, cache neuf ; **graine 7 sur la 3060 (Vulkan b11205), graines 42 et 123 sur la 3080** ; les deux modèles d'une même graine sur la même carte ; contrôles 6/6 FR et EN avant et après sur chaque carte |
| Statistiques | `g4b/g4b_eval.py` (enveloppe de `g3b/g3b_eval.py`), i5 résumé par `g4/g4_i5.py` ; chiffres dans `g4b/eval/g4b-eval.json`, i5 dans `g4b/eval/i5-summary.json` |
| Hors dépôt | 3080 `/root/steph-ft/g4b/` (runs, verdicts) ; 3060 `/mnt/backup-hdd/stephbench-tmp/gemma/g4b/judge/` ; i5 `/root/g4b/` |

Sha256 des runs (16 premiers) : Q4_0 `373b3d5c` `de6d3bf3` `460fd27f` ; `off-ple3` `585fefb2` `efac5deb` `31cda324` (graines 7, 42, 123).

## Écarts et incidents

| Écart | Effet |
|---|---|
| 3080 partagée avec G5 (entraînements, 4,5 Go de VRAM) | premiers lancements avortés (`llama-server arrêté au chargement`, 3 faux `rc=0`), runs effacés et relancés, garde de mémoire libre abaissée à 3 000 Mo ; débit divisé par deux pendant la génération |
| Ollama arrêté par moi à 01:38, relancé à 01:39 ; G5 l'a rearrêté ; relancé par `judge.sh` à 04:00 | Ollama actif à la fin, sans modèle chargé |
| Files de travaux : un couloir tué en cours d'attente, un travail relancé en double | run `g3b-q4` graine 7 produit par le processus orphelin, valide (1 308 lignes, sha256 égal à celui copié sur la 3060) ; aucun run compté deux fois |
| **`kill` par liste de processus sur la 3060 à 03:54** : un `judge_x3.py` de G5 (`g5j`, juge dev `a-sft-dev-b7`) a été tué avec les miens | son pilote l'a relancé dans la minute (`41 repris du cache`) ; perte : quelques minutes de jugement de G5, pas de donnée ; à signaler à G5 |
| Juge sur la 3060 (Vulkan) 4 fois plus lent que sur la 3080 | seed 123 relancée sur la 3080 (une seule carte par graine) ; deux runs de la 3060 (q4 graine 42, seed 123) abandonnés, non comptés |
| Harnais L5 générique `8d90a662`, pas `705fdcb9` (qui est le harnais affiné pour v1.0) | le Gemma tourne en production avec le prompt générique, comme en G3b |
| Jugement des 6 runs mêlant 3060 (graine 7) et 3080 (graines 42, 123) | apparié par graine sur une même carte ; effet carte non mesuré |

## Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| `off-ple3` de G3b : 540 tenseurs sur 541 égaux à G3b Q4_0, PLE seul en Q3_K | VÉRIFIÉ | comparaison de type et de md5 par tenseur, `gguf-py` b11205 ; échouerait si une couche différait | non archivée en script dans le dépôt |
| Aucune perte significative de qualité, de note de production, ni de langue | VÉRIFIÉ | `g4b/eval/g4b-eval.json`, 3 graines, IC couvrant 0 ; échouerait si un IC excluait 0 par le bas | puissance : un écart d'un point de qualité n'est pas exclu ; formulation à l'oral non repassée |
| Inventions non plus élevées | VÉRIFIÉ | +1,07 [-0,36 ; +2,54], 2 477 verdicts par modèle, contrôles 6/6 avant et après | tendance positive ; un seul juge (9B) ; effet de carte |
| Contrôle du banc | VÉRIFIÉ | Q4_0 regénéré : 3 924 réponses sur 3 924 identiques à G3b | - |
| RAM -879 Mo, 1er jeton inchangé sur l'i5 | EXÉCUTÉ | 2 passes par modèle, `g4b/eval/i5-summary.json` ; la RAM diffère de 3 Mo entre passes | 51 résumés seulement ; RAM steph et Piper reprise de Q1 ; i5 partagé non exclu hors charge < 0,3 |
| Qualité à l'écoute | JAMAIS EXÉCUTÉ | - | personne n'a écouté une réponse de `off-ple3` |
