# Recherche : obsolescence du modèle affiné et réentraînement

Tâche H2 du journal de mission interne (non publié). Rédigé le 2026-09-27. Entrées : `docs/research-steph-features.md` (H1),
`bench/matrix/finetune/labeled/train.jsonl`, `src/steph/prompts.py`, `src/steph/narrator.py`, `benchmark/data/v1/`.

## Verdict

- Le modèle affiné actuel ne sait faire **qu'une tâche** : le résumé français d'une commande terminée.
- Il sera **obsolète dès que steph l'utilise pour autre chose** : F10, questions, progression, annonce de début.
  steph n'a qu'un serveur LLM (`src/steph/llm.py`) : le modèle universel sert aussi ces modes.
- Recommandation : **un seul entraînement final multi-tâches, français et anglais**, après les nouveaux digests.
  Les entraînements actuels (A5) servent à choisir la taille du modèle, pas à livrer.

## Faits mesurés sur le corpus

Script Python lancé une fois sur `labeled/train.jsonl` (3 538 lignes).

| Constat | Valeur | Conséquence |
|---|---|---|
| Prompts système distincts | **1** (`Tu lis la sortie d'une commande...`, 3 538 sur 3 538) | aucun autre mode appris |
| Ce prompt dans `prompts.py` | **absent** : ni `SUMMARY_SYSTEM`, ni aucun autre | B3 doit l'ajouter ; tout mode passe par un prompt jamais vu |
| Structure des messages | `system, user, assistant` : 3 538 | aucun historique multi-tours (le mode questions en a un, `narrator.py:241-250`) |
| Taille de l'entrée utilisateur | médiane 262 car., p95 1 433, max 1 816 | questions : historique jusqu'à 36 000 car. (`config.py:72`), 20 fois plus |
| Longueur des réponses | 6,7 mots en moyenne, 25 au plus | détail : 60 mots, 3 à 5 points (`prompts.py:23`) |
| Statuts | succès 1 987, échec 1 545, signal 6 ; **« inconnu » 0, « interrompue » 0** | REPL et ssh (`narrator.py:698`, statut `None`) et Ctrl+C jamais vus |
| Durée au-delà de 60 s | **0** | progression et flux jamais vus |
| Réponses commençant par « Échec » | 1 613 | forme d'échec bien apprise |
| Entrées avec 3 lignes d'erreur ou plus | 85 | multi-erreurs présentes, peu nombreuses |
| `gcc`, `make`, `clang`, `cargo` | 140, 110, 10, 45 | erreurs de compilation couvertes |
| Traces Python | 132 | couvertes |
| Lancements de tests (pytest, jest, vitest, cargo test, go test) | **0** (le seul « pytest » est `pip install pytest`) | résultats de tests hors distribution |
| `git status`, `log`, `show`, `diff` | 62, 60, 57, 29 | git couvert, diff à la marge |
| Vrais flux `-f` (`tail -f`, `journalctl -f`, `docker logs -f`) | **0** (les 7 « -f » de H1 sont d'autres options) | mode flux jamais vu |
| `top -b -n1`, `top -l 1`, `docker top` | 5 et 6 | instantané de `top` couvert à la marge |
| `less`, `man`, `vim` | 0 | pages plein écran jamais vues |
| Tableaux bruts (`ls -l`, `ps`, `docker ps`) | 178, 34, 11 | tableaux bruts couverts |
| Sorties tronquées (marqueur d'omission) | 251 | troncature connue |
| Sorties à dominante anglaise / française | 1 298 / 397 | **l'anglais en entrée est déjà appris** ; seule la réponse est toujours française |
| Réponses en anglais | 0 | anglais en sortie jamais appris |
| Écritures non latines, messages espagnols ou allemands | 0 | autres langues absentes |

Banc `benchmark/data/v1/` : 105 cas en français, 105 en anglais, dont 9 questions et 8 résultats de tests par langue.

## Effet de chaque fonctionnalité sur le modèle

Légende : **1** ne touche pas le modèle ; **2** entrée changée, déjà couverte, généralisation probable ;
**3** nouvelles données d'entraînement exigées. « 2 ? » : douteux, un test tranche (section suivante).

| # | Fonctionnalité | Effet | Preuve |
|---|---|---|---|
| 1 | Coexistence lecteur d'écran | 1 | sortie audio seulement |
| 2 | Erreurs multiples, compte + première | **2 ?** si le compte est calculé en code | 85 entrées à 3 erreurs, 1 613 « Échec », règle du compte recopié déjà apprise (`30 éléments : a, b, c`) ; **3** si le modèle doit compter lui-même |
| 2b | Navigation erreur suivante | 1 | lecture de la ligne parsée, sans modèle |
| 3a | F10 (`DETAILS_SYSTEM`) | **3** | 0 exemple ; 60 mots contre 25 au plus |
| 3b | Questions (`QA_SYSTEM`) | **3** | 0 exemple multi-tours ; entrée 20 fois plus longue |
| 3c | Progression (`PROGRESS_SYSTEM`) | **3** | 0 durée au-delà de 60 s ; format d'entrée différent (`prompts.py:61`) |
| 3d | Annonce de début (`START_SYSTEM`) | **3** | la commande seule en entrée, jamais vue |
| 4a | `less` / `man` page par page | 1 | lecture verbatim de la page |
| 4b | Instantané de `top` / `htop` | **2 ?** | 5 `top -b` et 6 `docker top` au corpus ; l'instantané d'écran a des codes de mise en page absents du corpus |
| 4c | Mode de `vim` | 1 | ligne d'état lue en code |
| 5 | Menus à flèches | 1 | diff d'écran, attribut inverse |
| 6 | Résultats de tests | **2 ?** | 0 lancement au corpus ; mais 8 cas `tests` au banc, et un digest « 142 réussis, 2 échoués : a, b » reprend la règle des listes |
| 7 | Sons de statut | 1 | audio seul |
| 8a | Tableaux en « colonne : valeur » (relecture) | 1 | relecture sans modèle |
| 8b | Résumé de tableaux | **2** si le tableau reste brut ; **3** si converti en clé-valeur | 178 `ls -l`, 34 `ps`, 11 `docker ps` bruts |
| 9 | Journaux en continu | **3** | 0 vrai flux, 0 statut « en cours » ; fenêtre glissante jamais vue |
| 10 | Anglais complet | **3** | 0 réponse anglaise ; entrée anglaise déjà apprise (1 298) |
| 11 | Relecture mot et caractère | 1 | sans modèle |
| 12 | Commande corrective insérable | **3** | forme « Commande : » du mode questions, 0 exemple |
| 13 | Écho clavier | 1 | sans modèle |
| 14 | Repères dans l'historique | 1 | sans modèle |
| 15 | Copie | 1 | sans modèle |
| 16 | Résumé de diff et git | **2 ?** | 29 `diff` et 57 `show` bruts ; **3** si un digest de diff change l'entrée |
| 17 | Sorties très longues par sections | **3** | résumés partiels en entrée, jamais vus |
| 18 | « Ce que j'ai manqué » | **3** | entrée multi-commandes, proche du mode questions |
| 19 | ssh, tmux, REPL | **2 ?** | chemin actuel `narrator.py:698` : statut « inconnu », 0 au corpus |
| 20 | Braille | 1 | sans modèle |
| 21 | WSL / PowerShell natif | 1 / **3** | WSL : sorties Linux ; PowerShell : 0 exemple |
| 22 | Autres langues | **2 ?** en entrée ; **3** en sortie | 0 écriture non latine ; le banc multilingue L2 tranche |
| 23 | Notification fin hors focus | 1 | sans modèle |
| 24 | Garde-fou destructeur | 1 | sans modèle |
| 25 | Profils de verbosité | 1 | réglage de code |
| - | Passe anglaise (F1a, F1) | **3** | voir n° 10 ; prompts, digest et messages parlés à traduire avant l'étiquetage |

Bilan : **13 à 1**, **3 à 2 certain**, **6 à « 2 ? »**, **10 à 3**. Le 3 domine par les modes de la n° 3 et la langue.

## Tests qui tranchent les cas douteux

Sur le GGUF affiné actuel (A6), contre le modèle de base de même taille. Seuil proposé : l'affiné garde au moins
80 % de faits et 0 interdit, comme A9 ; sinon, la fonctionnalité passe en 3.

| Cas douteux | Cas à ajouter au banc (FR et EN) | Ce qui ferait échouer |
|---|---|---|
| 2 multi-erreurs | 6 builds `gcc`, `tsc`, `rustc` à 5 à 20 erreurs, avec ligne de compte en tête | compte faux, première erreur absente, plus de 25 mots |
| 4b `top` | 4 instantanés `top`, `htop` en 80x24 | processeur ou processus inventés |
| 6 tests | les 8 cas `tests` existants + 4 `jest`, `cargo test`, `go test` | noms de tests échoués faux ou absents |
| 16 diff | 4 `git diff` de 3 à 10 fichiers | compteurs +/- inventés |
| 19 REPL | 5 cas statut « inconnu » (python, node, psql, ssh) | « Échec » affirmé sans preuve |
| 22 langues | 6 sorties en `LANG=es_ES`, `de_DE`, `zh_CN` | cause mal traduite ou inventée |

Coût : environ 60 cas par langue, une passe Xeon, moins d'une heure.

## Stratégie recommandée

1. **Un seul entraînement final** : résumé, détail, questions, progression, début, en français et en anglais,
   avec un prompt système court par mode (5 prompts constants, pas un seul).
2. **Digests avant corpus** : erreurs multiples, tests et flux changent l'entrée ; les écrire en code avant
   d'étiqueter, sinon le corpus décrit une entrée qui n'existera plus.
3. **A9 ne livre pas** : il retient **2 finalistes de taille** sur le résumé FR ; le choix définitif se fait après
   l'entraînement unique, sur le banc complet (modes et langues).
4. **H3 et K3 fusionnent** en un seul réentraînement ; les deux variantes de K3 restent (suite du modèle affiné contre
   départ de zéro), suivies en temps réel par K0.
5. **Multilingue en entrée seulement dans le corpus unique** (sorties localisées, réponse FR ou EN) ; un 3e
   entraînement n'a lieu que si L2 échoue.

## Coût estimé

Estimations écrites à partir des débits mesurés ; aucune n'a été exécutée.

### Volume de corpus à ajouter

| Lot | Exemples FR | Source | Collecte nouvelle |
|---|---|---|---|
| Détail (F10) | 800 | entrées existantes, réétiquetées avec `DETAILS_SYSTEM` | non |
| Début | 400 | commandes existantes | non |
| Progression | 600 | fenêtres glissantes des sorties longues existantes (apt, pip, docker, make) | non |
| Questions et « Commande : » | 1 500 | sessions composées de 3 à 8 exécutions existantes, questions par gabarits | non (gabarits à écrire) |
| Résultats de tests | 200 | pytest, jest, vitest, cargo, go sur les machines de test | **oui** |
| Flux | 200 | fenêtres de `journalctl`, `docker logs`, serveurs de dev | en partie |
| Erreurs multiples | 150 | builds cassés à dessein | **oui** |
| **Total FR ajouté** | **3 850** | | |
| Miroir anglais | 7 400 | entrées `LANG=C` (1 298 déjà anglaises réétiquetées en anglais) | en partie (K2) |
| **Total à étiqueter** | **11 250** | | |

### Temps GPU

| Étape | Hypothèse | Estimation |
|---|---|---|
| Étiquetage court (résumé, début, progression, tests, flux) | 3060 + 3080 en parallèle, 88 + 185 = 273/min | 6 400 ex. : **25 min** |
| Étiquetage détail | réponses 4 fois plus longues : environ 70/min combinés | 1 600 ex. : **25 min** |
| Étiquetage questions | contexte 8 000 car. : environ 1/4 du débit, 68/min | 3 000 ex. : **45 min** |
| **Étiquetage total** | marge de reprise comprise | **1 h 30 à 2 h** |
| Entraînement Gemma 270M, A1000 | 8 min pour 6 135 ex.-époques ; environ 10 000 ex. gardés x 3 ; questions 10 fois plus coûteuses | **1 h 30 à 2 h 30** par variante |
| Entraînement Luth-0.6B | environ 2,5 fois Gemma | **4 à 6 h** par variante |
| Deux variantes (suite, zéro) x deux finalistes | 4 entraînements | **12 à 17 h** machine, en parallèle sur 3 machines : **une nuit** |

Le coût dominant est la longueur des entrées du mode questions. Plafonner l'historique à 8 000 caractères pour le petit
modèle divise ce coût par 4, et réduit la latence sur l'i5.

## Changements proposés au graphe de mission

| ID | Tâche | Dépend de | Changement |
|---|---|---|---|
| K1 | Test du modèle affiné actuel sur les cas anglais **et les 6 lots douteux ci-dessus** | A6, C1b | élargie |
| F2 | Digests en code : compte d'erreurs multiples, résultats de tests, filtre de flux ; TDD | H2 | **nouvelle** |
| H3 | Corpus multi-tâches : détail, début, progression, questions, tests, flux, multi-erreurs ; collecte et étiquetage FR | F2, F1a, A3 | **redéfinie** : corpus seulement, plus d'entraînement |
| K2 | Corpus anglais, plus sorties localisées en entrée (multilingue) | F1a, F2, A3, L1 | L1 et F2 ajoutés |
| A9 | Choix de **2 finalistes de taille** sur le résumé FR | A8 | redéfinie |
| K3 | Entraînement unique multi-tâches FR + EN, deux variantes, suivi K0 | K0, K1, H3, K2, A9 | H3 ajouté ; remplace le réentraînement de H3 |
| A9b | Choix définitif du modèle universel sur le banc complet (modes, FR, EN), vitesse i5 | K3 | **nouvelle** |
| B3, B4, A10, D3 | intégration, catalogue, publication, graphiques | A9b au lieu de A9 | dépendance déplacée |
| I2 | Jeu d'entraînement publié | A9b, K3 | publie le corpus final, pas le corpus FR |
| L2 | Banc multilingue | L1, K3 | inchangé ; L3 ne réentraîne que si L2 échoue |

Le chantier anglais demandé (C1b, F1a, K0, K1, K2, K3, L1, L2, L3) est déjà au graphe ; ces changements l'articulent
avec H3 pour éviter deux entraînements.

## Niveau de preuve

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| Composition du corpus (tableau des faits) | EXÉCUTÉ | scripts Python lancés une fois sur `labeled/train.jsonl` | copies `final/` distantes non contrôlées ; heuristique de langue par mots outils, approximative |
| Un seul prompt, absent de `prompts.py` | EXÉCUTÉ | comptage des `messages[0]` ; lecture de `src/steph/prompts.py` | le prompt de `train_lora.py` (K0) n'est pas relu |
| Un seul serveur LLM pour tous les modes | ÉCRIT | lecture de `src/steph/llm.py`, `narrator.py:244,505,515,611,645` | aucun lancement de steph |
| Classement 1, 2, 3 | ÉCRIT | raisonnement sur les faits ci-dessus | les « 2 ? » restent à trancher par K1 |
| Volumes et temps GPU | ÉCRIT | extrapolation des débits mesurés | débit réel des questions à contexte long jamais mesuré ; taux de doublons du futur corpus inconnu |
