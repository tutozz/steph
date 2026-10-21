# D4 : questions (F7) à outils en lecture seule

Date : 2026-09-29. Demande utilisateur : « donner des tools au modèle en read-only ».
Numéro de tâche : **D4** (la demande disait D2, déjà pris par le réalignement du master).

## Verdict

| Modèle | Mode outils contre mode actuel | Recommandation |
|---|---|---|
| **Gemma 4 E2B brut** | qualité questions **-9,9 pts** (IC [-21,5 ; 2,0]), réponse présente -15,1, inventions x2,2 | **ne pas activer** |
| **Qwen3.5 4B brut** | qualité questions **+7,4 pts** (IC [-3,2 ; 17,7]), réponse absente +19,4, inventions / 1,7 | à confirmer au split test avant d'activer |
| steph-speak v1.0 | n'appelle jamais d'outil ; repli à 100 %, qualité identique, environ 4,5 s perdues (serveur Xeon) | ne pas activer |

- Le mode outils **ne gagne pas partout** : il dépend du modèle. Aucun écart n'est significatif sur les 45 questions dev.
- Sur l'i5, à froid, il **supprime la queue longue** : premier fait p90 **35,3 s contre 57,4 s**, max 36,9 s contre 208 s.
  La médiane empire : 28,1 s contre 19,0 s. Préchauffé, le mode actuel gagne nettement : p90 2,2 s
  contre 19,6 s.
- Le réglage `qa_tools` reste **désactivé par défaut**. Le format P20 de l'affinage G3 est inchangé.

## 1. Ce qui a été construit

| Élément | Fichier |
|---|---|
| Quatre outils sur la `Session` : `search_history`, `get_output`, `command_info`, `count_matches` | `src/steph/qa_tools.py` |
| Boucle d'appels : 1er tour à appel imposé, plafonds, repli sur le mode actuel | `src/steph/qa_tools.py` (`ask_with_tools`) |
| Tour sans flux avec `tools` et `tool_choice` | `src/steph/llm.py` (`LLM.chat`) |
| Branchement derrière `qa_tools`, ancrage sur ce que le modèle a lu | `src/steph/server.py` (`_ask`) |
| Pas de préchauffage de l'historique en mode outils | `src/steph/narrator.py` (`_maybe_warm`) |
| Réglages : `qa_tools = false`, `qa_tools_max_calls = 3`, `qa_tools_result_chars = 2500`, `qa_tools_timeout_seconds = 45` | `src/steph/config.py` |
| Tests (47) | `tests/test_qa_tools.py` |
| Harnais P20 en mode outils, graine, régime préchauffé outils | `bench/matrix/p20_qa_latency.py` |
| Tableau, écart apparié par bootstrap | `bench/matrix/d4_summary.py` |

Entrée du modèle en mode outils : prompt système court, liste des commandes
(`[id] dossier $ commande   (code, durée, lignes)`), dossier actuel, question. Aucune sortie.

### Invariant de lecture seule

| Contrôle | Ce qui le ferait échouer |
|---|---|
| `test_tools_never_touch_files_network_processes_or_another_session` | un outil qui appelle `open`, `os.open`, `listdir`, `scandir`, `system`, `popen`, `subprocess.Popen`, `socket.socket`, `Path.read_*`, ou qui rend une chaîne d'une autre `Session` |
| `test_qa_tools_module_imports_nothing_that_can_reach_outside_the_session` | un import hors de `json`, `re`, `time`, `dataclasses`, `typing`, `prompts`, `session`, `strings`, ou un appel à `open`, `eval`, `exec`, `getattr`, `__import__`… |
| `test_only_the_four_tools_can_be_called` | un nom d'outil hors des quatre (`read_file`, `run_command`, `open`, méthodes internes) |

Mutations vérifiées : `import os` ajouté, lecture de fichier sur motif `/…`, lecture des autres
sessions par `gc.get_objects()`. Chacune fait échouer au moins un des tests ci-dessus.

## 2. Gabarits d'appel d'outils, llama.cpp b11205

| Modèle | Format détecté | Appel d'outil décodé | Remarque |
|---|---|---|---|
| Gemma 4 E2B (QAT q4_0, `fa401b55…`) | `peg-gemma4` | oui, `tool_calls` JSON | avertissement `<\|tool_response>` non contrôle au chargement, sans effet mesuré |
| Granite 4.0 H 350M brut (Q8_0) | analyseur automatique | oui (`count_matches` bien formé) | réponse finale fausse (« failed with 22 tests ») |
| steph-speak v1.0 (Granite affiné) | analyseur automatique | **non**, même avec `tool_choice: required` | texte libre ; jamais entraîné aux outils |
| Qwen3.5 4B (Q4_K_M) | analyseur automatique | oui | - |

Cache de préfixe entre tours : 439 jetons repris sur 500 (Gemma), 742 sur 781 (Qwen).

## 3. Réglage du prompt sur le split dev

Gemma écrit ses appels **en texte** (`count_matches 1 "FAILED"`) dès que le prompt système porte le
style télégraphique ou la règle « Pas dans l'historique ». Cinq variantes sur 12 cas dev, FR et EN,
graine 7, sans ancrage (`explore/`) :

| Variante | Qualité | Présente | Absente | Tours |
|---|---:|---:|---:|---:|
| V1 : système court, règles collées à chaque résultat d'outil | 72,9 | 69,4 | 83,3 | 1,9 |
| V2 : 1er appel imposé, pas de règles | 60,0 | 61,1 | 56,7 | - |
| V3 : 1er appel imposé, tour final de style | 68,8 | 80,6 | 33,3 | 3,6 |
| **V4 : V1 + 1er appel imposé + fenêtre `get_output` élargie** | **81,2** | 80,6 | 83,3 | 2,0 |
| V5 : V1 + fenêtre élargie | 72,9 | 75,0 | 66,7 | 1,9 |
| mode actuel, mêmes 24 évaluations | 77,1 | 69,4 | 100 | 1 |

V4 est retenue. Sur les 90 évaluations, un second défaut est apparu : Gemma lit `count: 1`, puis
20 lignes, et rate le résumé en fin de sortie (« 2 failed, 7 passed »). Correction : une fenêtre de
moins de 20 lignes devient la sortie entière, tête et queue gardées au-delà du plafond.
Risque assumé : ces réglages sont calés sur le split dev qui sert aussi à la mesure.

## 4. Qualité (banc v3 dev, questions, 3 graines)

Méthode : vrai chemin de production (`Session`, `Narrator`, `ControlServer._ask`, ancrage compris),
profil generic pour les bruts et finetuned pour v1.0, 45 questions x FR et EN = 90 évaluations par
graine, graines 7, 42 et 123 passées au serveur, échantillonnage de production (0,3 / 0,9 / 400).
Slot 1 vidé avant chaque question. CPU serveur Xeon (`AllowedCPUs=0-31`, `MemoryMax=32G`, nice 19),
llama-server b11205, 10 à 16 fils. Écart apparié : unité le cas (moyenne des graines et des langues),
bootstrap 10 000 tirages. Présente et absente : champ `answer_in_history` (204 et 66 évaluations).

| Modèle | Mode | Qualité (score_v3) | Graines 7 / 42 / 123 | Présente | Absente | score_production | Appels par question | Repli |
|---|---|---:|---|---:|---:|---:|---:|---:|
| Gemma 4 E2B | actuel | **77,5** | 74,6 / 77,8 / 80,0 | 76,6 | 80,3 | 79,7 | - | - |
| Gemma 4 E2B | outils | 67,6 | 69,1 / 69,4 / 64,3 | 61,5 | 86,4 | 69,8 | 1,03 | 0 % |
| Qwen3.5 4B | actuel | 70,9 | 72,8 / 68,0 / 71,9 | 77,6 | 50,0 | 73,1 | - | - |
| Qwen3.5 4B | outils | **78,2** | 79,4 / 75,7 / 79,6 | 81,1 | 69,4 | 80,5 | 1,04 | 0,4 % |
| v1.0 | actuel | 55,0 | 54,8 / 55,7 / 54,6 | 51,8 | 65,2 | 55,0 | - | - |
| v1.0 | outils | 55,0 | identique | 51,8 | 65,2 | 55,0 | 0 | 100 % |

| Écart outils - actuel | Points | IC 95 % |
|---|---:|---|
| Gemma 4 E2B | -9,9 | [-21,5 ; 2,0] |
| Qwen3.5 4B | +7,4 | [-3,2 ; 17,7] |
| v1.0 | 0,0 | [0,0 ; 0,0] |

- Appels : presque toujours **un seul** (Gemma 89 questions sur 90, Qwen 87). `get_output` domine.
- Première version (avant la correction de l'ancrage, section 6) : Gemma 67,4, Qwen 75,5 ; écart
  entre passes du même code de l'ordre de 3 points, le CPU multi-fil n'est pas déterministe.
- v1.0 sans le repli « aucun appel au 1er tour » : **12,5** ; il répondait en texte libre sans règles.

## 5. Inventions (juge A7, graine 7)

Juge A7 (`judge_lib_a7.py`, Qwen3.5-9B Q4_K_M `03b74727…`), 2 passes, sur **CPU serveur Xeon** : aucune
carte libre (3060 et 3080 prises par l'affinage Gemma, A1000 par le banc G3). Contexte jugé :
l'historique P20 complet du cas, identique pour les deux modes. Réponses « Pas dans l'historique. »
seules comptées justes sans passer au juge. Erreurs de contexte (slot de 8 192) rejugées avec 32 768.

| Modèle | Mode | Inventions / réponses | Taux | Taux hors abstentions | Douteux |
|---|---|---:|---:|---:|---:|
| Gemma 4 E2B | actuel | 6 / 90 | 6,7 % | 9,2 % (6/65) | 6 |
| Gemma 4 E2B | outils | 13 / 90 | 14,4 % | 21,0 % (13/62) | 2 |
| Qwen3.5 4B | actuel | 12 / 90 | 13,3 % | 15,6 % (12/77) | 4 |
| Qwen3.5 4B | outils | 7 / 90 | 7,8 % | 9,3 % (7/75) | 3 |

Qwen outils, première version du code : 5 / 90 (5,6 %). Les inventions de Gemma en mode outils sont
surtout des comptes faux après une lecture partielle : « 10 fichiers objets » pour 8, « big.log has
420 lines », « 1 installed formula » pour 354.

## 6. Défauts trouvés en passe adverse

| Défaut | Effet | Correction |
|---|---|---|
| Prompt système avec style et règle d'absence | Gemma n'appelle aucun outil, écrit l'appel en texte | règles collées au résultat de chaque outil (`QA_TOOLS_ANSWER`) |
| `get_output` avec `count: 1` | lecture d'une ligne, puis « Pas dans l'historique » | fenêtre < 20 lignes = sortie entière, tête et queue |
| Modèle qui ignore `tool_choice: required` (v1.0) | réponse libre sans règles, qualité 12,5 | pas d'appel au 1er tour = repli sur le mode actuel |
| Numérotation « 22: » des résultats dans la preuve d'ancrage | un compte inventé (« 22 lignes ERROR ») passait l'ancrage | numérotation retirée de la preuve ; mesures refaites (tableaux ci-dessus) |
| Préchauffage P20 actif en mode outils | lecture de tout l'historique au repos pour rien (jusqu'à 100 s de CPU sur l'i5) | désactivé quand `qa_tools` est vrai |
| Tour d'outils sur le slot 1 | le préfixe préchauffé est écrasé | `_qa_cached` oublié après une réponse à outils |

## 7. Latence sur l'i5-7200U (Gemma 4 E2B brut)

i5, 4 fils, llama-server b11205, réglages generic de production (`-c 32768 --parallel 2 -b 512 -ub 512`),
GGUF téléchargé sur l'i5, sha256 `fa401b55…` identique à G2. Une passe à la fois, charge < 0,3 et
aucun `llama-server` avant chaque passe. 20 questions dev FR (un cas sur deux, 15 réponses présentes),
graine 7. « Premier son » : premier morceau remis au haut-parleur (phrase « Je regarde
l'historique. »). « Premier fait » : premier morceau de réponse envoyé à la fenêtre ; en mode
outils, la réponse arrive d'un bloc.

| Régime | Mode | Premier fait médiane | p90 | max | Premier son p90 | Appels |
|---|---|---:|---:|---:|---:|---:|
| froid (slot vidé) | actuel | **19,0 s** | 57,4 s | 208,3 s | 0,005 s | - |
| froid (slot vidé) | outils | 28,1 s | **35,3 s** | **36,9 s** | 0,006 s | 1 par question |
| préchauffé | actuel | **1,9 s** | **2,2 s** | 6,4 s | 2,2 s (pas de phrase) | - |
| préchauffé (préfixe outils lu) | outils | 8,0 s | 19,6 s | 30,5 s | 0,004 s | 1 par question |

- Froid : le mode actuel lit tout l'historique (jusqu'à 9 579 caractères, 208 s) ; le mode outils
  lit système + outils + liste, puis une sortie. Son coût est à peu près constant, d'où le p90.
- Préchauffé : le mode actuel ne paie que la question ; le mode outils paie toujours deux tours et
  la génération de l'appel (environ 25 jetons à 11 jetons/s). Steph ne préchauffe pas encore le
  préfixe outils : ce régime suppose une question précédente sur la même session.
- Code des passes i5 : avant la correction de l'ancrage et du repli v1.0, sans effet sur Gemma
  (aucune réponse sans appel, aucun repli).

## 8. Recommandation

- **Gemma 4 E2B brut : ne pas activer.** Qualité -9,9, inventions doublées. Le gain de p90 à froid
  sur l'i5 ne compense pas, et le préchauffage actuel reste plus rapide.
- **Qwen3.5 4B brut : candidat.** +7,4 en qualité, inventions 7,8 % contre 13,3 %, absentes +19,4. À confirmer
  au split test (70 questions) avant tout changement de défaut ; Qwen 4B n'est pas un modèle du
  catalogue aujourd'hui.
- **Prochain affinage (G3) : ne pas y entrer maintenant.** Le format P20 donne 77,5 à Gemma brut et
  G3 l'apprend déjà. Un affinage aux outils demanderait un corpus de conversations à outils et
  changerait le format d'entrée. À rouvrir si un Gemma affiné plafonne sur les questions à réponse
  présente dans des sessions longues, là où le mode outils garde un coût constant.
- Pistes non mesurées : préchauffer le préfixe outils, réponse en flux au dernier tour, plafond de
  temps adapté à la machine (45 s tient sur l'i5 à froid, max 36,9 s).

## Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| Outils limités à la session, sans fichier, réseau, exécution ni autre session | VÉRIFIÉ | `tests/test_qa_tools.py`, 3 tests d'invariant, 3 mutations qui les font échouer | pas d'audit par un tiers ; `Session` elle-même non auditée |
| Réglage désactivé par défaut, mode actuel inchangé | VÉRIFIÉ | `test_config_keeps_the_tool_mode_off_by_default`, `test_default_config_never_uses_the_tool_mode` ; 5 345 tests verts après rebase sur master | pas de session réelle avec F7 et `qa_tools = true` |
| Gemma : outils -9,9 pts | EXÉCUTÉ | `runs/gemma-*.json`, `d4_summary.py --pair` | IC traverse 0 ; réglé et mesuré sur le même split dev ; split test non lu |
| Qwen 4B : outils +7,4 pts | EXÉCUTÉ | `runs/qwen-*.json` | IC traverse 0 ; split test non lu |
| Inventions | EXÉCUTÉ | `judge/verdicts-*.json` | graine 7 seulement ; juge sur CPU, non revalidé dans cette session |
| i5 à froid : p90 35,3 contre 57,4 s ; préchauffé : 19,6 contre 2,2 s | EXÉCUTÉ | `i5/*.json`, `i5/run.log` (charge < 0,3 avant chaque passe) | une passe par régime, 20 questions FR seulement ; son réel Piper non capté ; préfixe outils préchauffé par une question « ok », pas par steph |
| v1.0 : repli à 100 % | VÉRIFIÉ | `runs/v10-tools2-*.json` identiques à `v10-cur` ; `test_a_model_that_ignores_the_required_first_call_falls_back` | - |
| Gabarits Gemma 4 et Granite 350M | EXÉCUTÉ | sondes `probe.py` sur serveur Xeon (section 2) | une requête par modèle |

RECETTE : personne n'a encore posé de question F7 avec `qa_tools = true` dans un vrai terminal.
