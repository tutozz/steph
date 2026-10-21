# Efficacité du petit modèle : synthèse des quatre pistes

Pistes comparées : audit du banc (facts v2), vocabulaire réduit, encodeur-décodeur T5, phrases construites en code (`resolve()` dans `src/steph/digest.py`).
Contraintes : premier mot < 3 s au 90e centile sur l'i5-7200U ; au plus 1 invention sur 36.

## Verdict

**À retenir : Granite 4.0 H 350M Q4 + `resolve()`.** C'est la seule combinaison qui tient les deux contraintes sur le banc, sous toutes les lectures du 90e centile.

- Seul, aucun modèle ne passe : le meilleur sous 3 s, Granite s42 Q4, fait **6 inventions confirmées**.
- Avec `resolve()`, le code écrit 28 phrases sur 36. Au modèle, il ne reste que 5 cas dans steph : fx09 (grep), fx29 (lspci), qa0, qa1 et qa2.
- Sur ces 5 cas, Granite s42 Q4 et la soupe uniforme Q4 font **1 invention** chacun (qa2). Les 28 phrases du code ne font **aucune invention confirmée** (voir plus bas).
- **Marge nulle** : 1 sur 36, c'est exactement le plancher, sur un échantillon de 5 cas.

Le vocabulaire réduit et T5 ne changent pas ce choix (détail plus bas).

## Tableau unique

Qualité : banc steph de 36 cas, `facts.v2.json`. « + resolve » : les 28 cas résolus reçoivent la phrase du code, les 8 autres gardent la sortie du modèle.
Inventions : juge A7 (Qwen3.5 9B, 2 passes), corrigées par `judge_audit.v2.json` quand l'audit les couvre.
Vitesse : i5-7200U, 4 threads, ctx 4096, `cases_ft36`. « p90 système » compte 0 s pour un cas résolu en code.

| Modèle | Qualité v2 seul | Qualité v2 + resolve | Inventions /36 seul | Inventions + resolve | TTFT p90 i5, 36 cas | TTFT max, 5 cas au modèle | p90 système + resolve | GGUF | RAM pic i5 |
|---|---|---|---|---|---|---|---|---|---|
| **Granite 350M s42 Q4** | 82,8 (i5) / 84,3 (3 graines) | **94,0** / 93,6 | 6 | **1** (qa2) | 2,30 s | **2,58 s** (fx29) | 0,78 s | 223 Mo | 2 545 Mo |
| Granite soupe uniforme Q4 | 80,4 / 81,9 | 92,3 / 92,5 | 7 (non audité v2) | **1** (qa2) | 2,21 s | 2,38 s (fx29) | 0,72 s | 223 Mo | 2 545 Mo |
| Gemma 3 270M s42 Q8 | 82,6 | 89,8 | 8 | 2 (fx09, qa0) | 1,71 s | 1,69 s | 0,82 s | 292 Mo | 691 Mo |
| Gemma s42 Q8, vocab corpus 64k | 82,6 (3 graines) | 89,3 | 13 (non audité v2) | 5 (non audité) | 1,70-1,79 s | non mesuré par cas | - | 153 Mo | 537 Mo |
| Gemma s42 Q8, vocab 32k | 80,6 (3 graines) | 87,3 | 14 (non audité v2) | 4 (non audité) | 1,69-1,71 s | non mesuré par cas | - | 130 Mo | 500 Mo |
| flan-t5-small Q8 | 72,4 (i5) | 85,1 | 16 (non audité v2) | 4 (non audité) | **0,70 s** | 0,73 s | 0,35 s | 83 Mo | non mesurée |
| flan-t5-base Q8 | 73,0 | 84,8 | 11 (non audité v2) | 1 (fx09, non audité) | 1,97 s | JSON resté sur l'i5 | - | 264 Mo | non mesurée |
| Qwen3.5 0.8B Q4 (fixed / jugé s42) | 86,8 | 91,2 | 2 | 1 (fx29 ou qa2 selon la graine) | **5,38 s** | **5,51 s** (fx29) | 1,57 s | 542 Mo | 2 802 Mo |

Lecture :

- **Le code rapporte plus que tout changement de modèle** : +7 à +14 points de qualité, et 5 à 6 inventions en moins sur Granite.
- **Qwen 0.8B passe le p90 système** (1,57 s) mais pas les cas qui atteignent le modèle : lspci à 5,5 s, qa0 à 3,1 s. Voir « Décision à prendre ».
- **Granite reste sous 3 s** même sur son pire cas au modèle (2,58 s).
- **Gemma est le plus léger en RAM** (0,7 Go contre 2,5 Go), mais invente deux fois sur ses 5 cas restants.

## Les 28 phrases du code passées au juge

Juge A7 revalidé avant usage (6/6 en passe A, 6/6 en passe B). Deux contextes testés, parce que le banc anonymise et tronque les sorties.

| Contexte | ok | invention | douteux |
|---|---|---|---|
| Sortie brute complète (fixtures du dépôt) | 18 | 9 | 1 |
| Entrée du banc (`cases.json`, anonymisée et digérée) | 21 | 5 | 2 |

Relecture cas par cas, un seul relecteur :

| Cas | Phrase | Verdict relu | Raison |
|---|---|---|---|
| fx08, fx24 | « pipewire actif depuis 2 jours », « 12 paquets mis à jour » | faux positif | le fait est dans la sortie brute ; le digest du banc le masque par `[…]` |
| fx30, ip_a_proxmox | adresses IP | faux positif | fixtures non anonymisées contre banc anonymisé (écart déjà noté par la piste 4) |
| fx12, fx26, fx11 | comptes d'éléments, de dépendances, de réseaux virtuels | faux positif | comptes refaits à la main : 6, 4, 8 (7 ponts + docker0) |
| fx04 | « string ligne 1 : KeyError key » | discutable | « ligne 1 » est dans la trace ; « string » vient de `<string>` |
| fx00, fx15, fx18, fx20 | « 37 / 20 / 30 / 29 éléments » après `head` ou `tail` | discutable | le compte porte sur l'affichage tronqué, pas sur le vrai total ; fx20 : l'audit tient déjà cette entrée pour défectueuse |
| **fx22** | « 9 conteneurs : shopapp_api, shopapp_nginx_admin, shopapp_vault » | **défaut réel** | `shopapp_vault` est en `Restarting (1)` ; la phrase le cite comme les autres. Omission, pas invention, mais c'est l'information utile |

**Aucune invention confirmée dans le code.** fx22 reste un défaut à corriger en TDD. Le cas TermSpeak `ctr-docker-ps-restarting` produit la même phrase.

## Ce que valent les deux autres pistes

**Vocabulaire réduit** (Gemma seulement) :
- Génération ×1,6 à ×2, RAM -150 à -200 Mo, fichier divisé par 2.
- Premier mot inchangé : il vient du traitement du prompt, pas de la tête de sortie.
- Inventions inchangées (13 à 15).
- Utile seulement si Gemma est retenu pour la RAM. Avec Granite, la génération (60 jetons/s) va déjà plus vite que la voix.

**T5** :
- Premier mot le plus rapide (0,70 s), mais 16 inventions et aucune question traitée.
- flan-t5-base + `resolve()` tombe aussi à 1 invention, mais ne répond pas aux questions (score nul sur qa).
- llama-server ne sait pas servir T5 : il faudrait un autre moteur dans steph.
- Écarté.

## Décision à prendre

**Sur quoi porte le 90e centile ?**

- Sur toutes les commandes : Qwen 0.8B passe aussi (1,57 s). Il a la meilleure qualité seule, mais pèse 542 Mo et 2,8 Go de RAM.
- Sur les commandes qui atteignent le modèle : seul Granite passe.

La recommandation Granite tient dans les deux cas.

## Reste à tester, par ordre de rendement

| # | Travail | Pourquoi | Coût estimé |
|---|---|---|---|
| 1 | Corriger fx22 (état des conteneurs), `prompts.py:42` (code 255 annoncé comme signal), `digest.py:201` (faux en-tête « N éléments » après `head`) | défauts réels trouvés par l'audit et par ce juge | 2 h, TDD, aucune machine |
| 2 | Questions : ajouter 100 à 200 exemples de questions au corpus, ou une règle « introuvable dans l'historique » en code | qa2 est la seule invention restante ; le corpus contient 0 question | règle : 2 h ; corpus : 4 h d'étiquetage et de juge sur RTX 3060, plus 1 h d'entraînement Granite sur la RTX 3060 |
| 3 | Faire tenir compte `make_cases.py` de `resolve()`, puis juger Granite sur la part non résolue de TermSpeak (113 cas sur 192) | le chiffre « 1 sur 36 » repose sur 5 cas ; TermSpeak n'est résolu qu'à 41 % | 1 h de code, 10 min de banc, 10 min de juge |
| 4 | Comprendre les 2,5 Go de RAM de Granite (fichier de 223 Mo) | Gemma tient en 0,7 Go ; les petites machines comptent pour ce public | 1 h de mesures sur l'i5 (`-c`, `--no-mmap`, état récurrent) |
| 5 | Distillation vers 100 à 150M (par exemple SmolLM2-135M, Apache-2.0, faible en français) avec 10 000 à 20 000 étiquettes | premier mot estimé vers 1 s sur l'i5, RAM plus basse | étiquetage 20 000 cas : environ 4 h d'enseignant et 8 h de juge (2 passes) sur la RTX 3060 ; entraînement complet environ 3 h ; **le vrai coût est de trouver 20 000 sorties réalistes**, le corpus brut n'en a que 2 414. Risque : T5 77M invente 16 fois avec les données actuelles |
| 6 | Entraînement de zéro, 20 à 60M | seule voie vers un modèle sous 100 Mo | pré-entraînement français : 20M sur 0,4 milliard de jetons, environ 1 à 2 h ; 60M sur 1,2 milliard, environ 12 à 24 h sur la RTX 3060 (6·N·D FLOPs, 10 TFLOPS utiles supposés) ; plus un tokenizer et un corpus libre de droits. **Risque d'invention le plus élevé** : à retenter seulement si la piste 5 réussit |

Les pistes 5 et 6 ne visent que la vitesse et la taille. Granite + `resolve()` tient déjà la vitesse ; elles ne se justifient que si la RAM de Granite ne se corrige pas.

## Fichiers

- Verdicts du juge sur les 28 phrases : `bench/matrix/results/finetune/efficiency/judge-resolve-{rawctx,benchctx}.json`
- Scripts : `bench/matrix/finetune/efficiency/{build_resolve_ctx.py,judge_resolved.py}`
- RTX 3060 : `/root/stephbench-matrix/judge/efficiency/` (mêmes scripts, contextes, sorties, `server.log`)

## Tableau de preuve

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| Qualité v2 seul et + resolve, toutes lignes du tableau | EXÉCUTÉ | calcul avec `rescore.quality` et `facts.v2.json` sur les fichiers de `results/finetune/` | facts v2 et `resolve()` ont été écrits en voyant ces 36 cas : le + resolve est un plafond, pas une mesure hors échantillon. fx13, fx14, fx23 gardent la sortie du modèle alors que steph les lit telles quelles |
| Inventions restantes + resolve (Granite 1, Gemma 2, Qwen 1) | EXÉCUTÉ | verdicts existants `judge-*.json` filtrés sur les 5 cas que steph envoie au modèle, audit v2 appliqué | 5 cas seulement ; soupe, vocab et T5 non audités v2 ; la sortie du modèle sur ces cas n'a pas été rejouée |
| 0 invention confirmée dans les 28 phrases du code | EXÉCUTÉ | juge A7 revalidé 6/6 A et B, 2 contextes ; relecture ci-dessus | un seul relecteur humain ; comptes de fx18 et ip_a_proxmox non refaits à la main |
| p90 système et TTFT max sur les 5 cas | EXÉCUTÉ | recalcul par cas depuis `rows[].ttft` des `i5-*.json` existants | aucun nouveau passage sur l'i5 ; coût de `resolve()` et de la synthèse vocale non mesuré ; Qwen mesuré sur la variante full, pas fixed |
| `resolve()` couvre 79 cas TermSpeak sur 192 (41 %) | EXÉCUTÉ | `resolve()` sur `benchmark/data/v1/*/*.jsonl`, tâches de résumé | phrases TermSpeak non jugées ; TermSpeak recoupe en partie le banc |
| Coûts des pistes 5 et 6 | ÉCRIT | estimation depuis les durées mesurées (juge 216 cas en 306 s, T5-base 18 min) et la règle 6·N·D | rien n'a tourné ; débit réel de la RTX 3060 non mesuré |
