# P14 : rebanc final, P17 contre P15

Décision A9. Candidat : P17 (DPO 12 époques sur la soupe P15). Référence : soupe P15.
Format B3 partout : TRAIN_SYSTEM, entrée plafonnée à 587 caractères
(`bench/matrix/cases_compact_granite200_train.json`).

Résultats bruts : `bench/matrix/results/finetune/p14/p14-summary.json`.

## Verdict par critère (plan A9)

| Critère | Cible | P17 mesuré | Verdict |
|---|---|---|---|
| Premier son p90 (i5, audio réel) | < 0,3 s | 0,189 s | **tenu** |
| Premier fait utile p90 | < 1 s | 1,299 s (modèle brut, 36 cas) ; 2,19 s (chemin complet, n=1) | **non tenu** |
| Inventions sur 36 (juge A7) | ≤ 1 | 4,3 à 5,0 en moyenne selon la graine, jamais sous 4 | **non tenu** |

2 critères sur 3 non tenus. Le plancher A9 n'est pas atteint par P17.

## 1. Latence brute i5 (P8, sans TTS)

`bench/perf/granite_ram.py`, réglages P8 (`-t 4 -ub 512 -b 512 -c 4096 --jinja -ngl 0`),
llama-b11205, i5-7200U, 36 cas.

| Modèle | 1er jeton médian | 1er jeton p90 | RAM repos avant | RAM repos après | RAM pic |
|---|---|---|---|---|---|
| P15 soupe uniforme | 0,603 s | 1,279 s | 449 Mo | 1954 Mo | 1954 Mo |
| P17 DPO ep12 | 0,646 s | 1,299 s | 449 Mo | 1954 Mo | 1954 Mo |

Même poids GGUF (223 Mo, même architecture Granite 4.0 H 350M), latence et RAM
indiscernables entre P15 et P17 : le DPO ne change ni la taille ni la vitesse.

Une série à la fois : le premier essai (P17) a été lancé pendant qu'un job RAM de l'agent
Q2c tournait déjà sur le même i5, contamination détectée par contention CPU, tué par PID,
rerun propre après vérification qu'aucun `llama-server`/`piper`/`parec` ne tournait.

## 2. Chemin complet i5 (P19, avec TTS et ancrage)

`bench/matrix/p19_harness.py`, 33 fixtures (`bench/fixtures.json` + `extra_fixtures.json` +
2 fixtures df/ip proxmox), voix Piper `fr_FR-siwis-medium`, session PipeWire de `user`.

**Bogue trouvé et corrigé** : le harnais committé appelait `narrator._llm_say` sans le
paramètre `suffix` (ajouté depuis dans `narrator.py` pour la durée dite après le flux du
modèle) ; le harnais plantait sur toute commande longue routée au modèle. Correction
minimale dans `p19_harness.py` (signature de `_spy_llm_say`), sans quoi aucune mesure P19
n'est possible avec le code actuel.

| Modèle | Son audible p90 (33 cas) | Fait utile audible p90, code (32 cas) | Fait utile audible, modèle (1 cas) |
|---|---|---|---|
| P15 soupe uniforme | 0,199 s | 0,199 s | 2,246 s |
| P17 DPO ep12 | 0,189 s | 0,189 s | 2,193 s |

Sur ces 33 fixtures, `resolve()` traite 32 cas sur 33 : un seul part au modèle. Le p90
« modèle » n'est donc qu'une valeur unique (n=1), pas une vraie statistique de percentile.
Le critère « premier fait utile < 1 s p90 » se lit mieux sur le banc brut de la section 1
(36 cas, tous envoyés au modèle) : 1,299 s p90 pour P17, au-dessus de la cible.

## 3. Qualité v2 (RTX 3080, 3 graines de banc)

Déjà mesuré sur le même harnais pour les deux modèles
(`bench/matrix/results/finetune/p17/p17-summary.json`), repris ici sans reprise de travail.

| Modèle | v2 total | v2 contrôle | v2 résumé seul | v2 « tel que dit » |
|---|---|---|---|---|
| P15 soupe uniforme | 80,9 | 72,2 | 79,2 | 83,7 |
| P17 DPO ep12 | **87,7** | **80,6** | **86,6** | **90,5** |

P17 gagne nettement sur la qualité (+6,8 pts v2 total, +8,4 pts contrôle).

## 4. Inventions, juge A7, avec et sans garde-fou d'ancrage P13

Juge A7 d'origine (`judge_lib` empreinte `079468ba...`, identique à
`bench/matrix/finetune/judge_lib_a7.py` à 2 lignes d'en-tête SPDX près), revalidé 6/6 passe
A et 6/6 passe B avant chaque usage.

| Modèle | Sans ancrage (moy. 3 graines) | Avec ancrage P13 (moy. 3 graines) |
|---|---|---|
| P15 soupe uniforme | 7,0 / 36 | 6,3 / 36 |
| P17 DPO ep12 | 5,0 / 36 | **4,3 / 36** |

Aucun des deux modèles n'approche le plancher de 1/36, avec ou sans ancrage.

**Défaut trouvé (garde-fou P13)** : sur `fx07` (P17, les 3 graines), le texte brut
« Mémoire 31G total, 24G disponibles. Swap 8G total, 72Ki disponibles. » devient après
ancrage « Mémoire 31G total, 24G disponibles. 72Ki disponibles. ». Le mot « Swap » (dans
`_TEMPLATE_WORDS` de `grounding.py`) est retiré de la phrase, ce qui laisse
« 72Ki disponibles » orphelin ; le juge compte alors ce fragment comme une invention alors
que le chiffre est exact et présent dans le contexte. L'ancrage dégrade ce cas au lieu de
le protéger. Reproductible sur les 3 graines P17, jamais corrigé dans ce rapport (hors
scope : P13 est une tâche fermée, ceci est une mesure).

## 5. Steph Speak Bench, part non résolue en code (split dev, FR/EN)

`benchmark/run.py`, TRAIN_SYSTEM (même texte français que la production, non traduit
même en EN : c'est le comportement réel de `prompts.py`), split dev, sur les cas où
`digest.resolve()` renvoie `None` (14 cas sur 39 par langue). Score `run.py` natif
(fact recall, pénalités interdits/longueur), pas le score v2 compact.

| Modèle | Score FR (14 cas) | Inventions FR | Score EN (14 cas) | Inventions EN |
|---|---|---|---|---|
| P15 soupe uniforme | 28,0 % | 2 / 14 | 25,0 % | 4 / 14 |
| P17 DPO ep12 | 21,4 % | 5 / 14 | 30,2 % | 5 / 14 |

Hors distribution d'entraînement (catégories, style TermSpeak plus varié que les 36 cas de
banc) : les deux modèles chutent nettement, et P17 n'est pas systématiquement meilleur ici
(plus d'inventions FR que P15). Cohérent avec un entraînement ciblé sur le format
36-cas/B3, pas sur la diversité de TermSpeak.

## Comparaison P15 / P17

| Axe | P15 | P17 | Meilleur |
|---|---|---|---|
| Latence i5 brute (p90) | 1,279 s | 1,299 s | égal (bruit de mesure) |
| RAM i5 | 1954 Mo | 1954 Mo | égal |
| Qualité v2 totale | 80,9 | 87,7 | **P17** |
| Inventions/36 sans ancrage | 7,0 | 5,0 | **P17** |
| Inventions/36 avec ancrage | 6,3 | 4,3 | **P17** |
| TermSpeak dev non résolu (FR+EN, score moyen) | 26,5 % | 25,8 % | égal |
| TermSpeak dev non résolu (FR+EN, inventions) | 6 / 28 | 10 / 28 | **P15** |

## Recommandation pour A9

**P17 reste le meilleur candidat mesuré** : +6,8 pts de qualité v2 et 2 à 3 inventions de
moins sur les 36 cas que P15, pour la même latence et la même RAM. Mais **le plancher A9
n'est pas atteint** : ni le critère de latence modèle (1,3 s contre 1 s visé), ni le
critère d'inventions (4 à 5/36 contre 1/36 visé). Le garde-fou d'ancrage P13 aide en
moyenne mais pas de façon fiable (un cas dégradé trouvé sur `fx07`), et la généralisation
hors distribution (TermSpeak dev) montre que le gain d'inventions de P17 ne se retrouve
pas systématiquement sur des cas nouveaux.

Suivant la règle A9 (« sinon itération A4-A8, 5 boucles au plus »), le plancher n'étant
pas tenu, la mission prévoit la distillation 100-150M (note P14 du suivi) comme option
suivante plutôt qu'un neuvième modèle affiné sur la même architecture.

## docs/models-table.md

`bench/matrix/models_table.py` scanne uniquement `bench/matrix/results/finetune/` (et
`vocab/`, `efficiency/`, `t5/`, pas de sous-dossier `p14/`) et attend soit un fichier de
banc brut (`rows[i].fixture`/`rows[i].out`), soit un des 4 fichiers `judge-*.json` fixes
qu'il connaît par leur nom exact (`judge-i5.json`, `judge-judged.json`, `judge-fixed.json`,
`judge-soup.json`). Il ne sait pas lire `p15-summary.json`/`p17-summary.json`/
`p14-summary.json` (format agrégé, pas de `rows[i].fixture`). Relancé tel quel : aucun
changement (`docs/models-table.md` inchangé), P15 et P17 n'y apparaissent pas sous ce nom.
Étendre le script pour ces formats est hors scope de P14 (mesure, pas outillage) : non
fait, signalé ici comme demandé.

## Nettoyage

| Hôte | Action |
|---|---|
| i5-7200U | GGUF P15/P17, cases, scripts et travail P19 retirés de `/root/stephbench-ft` et `/root/p14-work` |
| RTX 3080 (labo) | serveur juge et serveurs modèle arrêtés, `systemctl start ollama` relancé |
