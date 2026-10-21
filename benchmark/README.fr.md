# Steph Speak Bench

**Un benchmark pour les LLM locaux qui lisent à voix haute la sortie du terminal.**

Steph Speak Bench mesure ce qu'un modèle de langage fait de la sortie d'une commande quand la
réponse est lue à une personne aveugle ou malvoyante : un résumé court, les faits exacts,
rien d'inventé, et le premier mot vite. Il vient de [steph](../README.fr.md), un terminal
parlant, et il est publié à part pour comparer n'importe quel modèle, prompt ou moteur sur
les mêmes cas.

[English](README.md)

## Pourquoi c'est dur

- **Petits modèles.** Un assistant vocal de terminal tourne à côté du travail de
  l'utilisateur, souvent sur le processeur d'un portable. Les modèles qui y tiennent (0,3 à
  4 milliards de paramètres) sont ceux qui paraphrasent, perdent les chiffres et recopient
  les exemples du prompt.
- **Faits exacts.** « Le build a échoué » ne sert à rien. Il faut le fichier, la ligne et
  la cause, l'espace libre en gigaoctets, l'IPv4 de l'interface VPN, le test en échec.
- **Hallucinations.** Une réponse parlée ne se relit pas en diagonale contre l'écran. Un
  processeur inventé dans un `lspci`, la boucle locale donnée comme adresse réseau, un
  mauvais nombre de conteneurs : chacun trompe.
- **Latence.** Un silence après une commande donne l'impression d'une panne. Le délai
  avant le premier mot compte autant que la qualité.
- **Sorties longues.** Journaux de compilation et mises à jour de paquets font des
  centaines de lignes ; le modèle en voit une version coupée et doit quand même trouver la
  ligne décisive.

## Ce qui est mesuré

| Mesure | Définition |
|---|---|
| Score | Moyenne des scores de cas, en %. Déterministe, voir [Barème](#barème) |
| Rappel des faits | Faits attendus trouvés / faits attendus, sur tous les cas |
| Interdit touché | Part des réponses avec un contenu interdit (invention, boucle locale, MAC, raisonnement qui fuit, markdown) |
| Trop long | Part des réponses au-delà du budget de mots du cas |
| TTFT médiane, p90 | Secondes entre la requête et le premier caractère parlé non blanc (raisonnement exclu) |
| Durée totale médiane, p90 | Secondes entre la requête et la fin de la réponse |
| tok/s | Vitesse de génération, médiane des cas, lue dans l'usage ou les timings du serveur |
| Juge : halluciné | Optionnel, part des réponses qu'un juge LLM déclare non étayées. Jamais mêlé au score |

Les scores sont donnés par langue, par split et par catégorie.

## Jeu de données (v1)

<!-- dataset-stats:start -->
| Catégorie | dev | test | réels anonymisés | synthétiques | total |
|---|---:|---:|---:|---:|---:|
| build-failure | 3 | 5 | 1 | 7 | 8 |
| runtime-error | 3 | 5 | 1 | 7 | 8 |
| tests | 2 | 6 | 0 | 8 | 8 |
| git | 3 | 5 | 2 | 6 | 8 |
| packages | 4 | 4 | 4 | 4 | 8 |
| network | 4 | 4 | 4 | 4 | 8 |
| disks | 4 | 4 | 3 | 5 | 8 |
| memory | 2 | 6 | 0 | 8 | 8 |
| hardware | 5 | 3 | 1 | 7 | 8 |
| containers | 3 | 5 | 1 | 7 | 8 |
| long-lists | 4 | 4 | 4 | 4 | 8 |
| long-truncated | 2 | 6 | 0 | 8 | 8 |
| history-qa | 4 | 5 | 3 | 6 | 9 |
| **total** | 43 | 62 | 24 | 81 | 105 |

105 cas par langue, sorties de 5 à 294 lignes (médiane 12).
<!-- dataset-stats:end -->

- **Langues.** Chaque cas existe en anglais, français, allemand, espagnol, portugais et
  russe sous le même identifiant (allemand, espagnol, portugais et russe ajoutés plus
  tard, modèles bruts seulement pour l'instant : voir
  [Banc multilingue](#banc-multilingue-modèles-bruts-seulement)). La
  sortie de commande est partagée quand l'outil écrit en anglais quelle que soit la locale
  (compilateurs, Python, docker) ; elle est localisée quand l'outil l'est (apt, df, git,
  ping, dates de ls). La question, les faits attendus et la réponse de référence existent
  dans chaque langue.
- **Origine.** Les cas `real-anonymized` ont été capturés sur de vraies machines Linux et
  macOS pendant le développement de steph, puis anonymisés à la main. Les cas `synthetic`
  ont été écrits pour le benchmark, à l'identique de l'outil réel. Chaque cas porte son
  origine.
- **Splits.** `dev` peut être lu et servir à régler prompts et paramètres. `test` sert
  uniquement à publier un score. Le split test ne contient que des cas synthétiques, et
  **aucun n'a jamais servi à entraîner ni à affiner les modèles de steph** : voir
  [Contamination](#contamination).
- **Tailles.** Les sorties font de 5 à 400 lignes. Au-delà de 3 500 caractères, le lanceur
  les coupe, comme le ferait un vrai assistant.

### Fichiers

```
benchmark/
  run.py                      lanceur et barème, un seul fichier, bibliothèque standard
  data/
    README.md                 fiche du jeu de données (datasheet, métadonnées Hugging Face)
    croissant.json            métadonnées Croissant 1.0 + RAI, avec sommes de contrôle
    v1/
      en/dev.jsonl  en/test.jsonl  fr/dev.jsonl  fr/test.jsonl
      schema.json             schéma JSON d'un cas
      prompts.json            prompts système, gabarits d'entrée, prompt du juge
      scoring.json            interdits globaux, budgets de mots, pénalité de longueur
  results/                    un JSON par exécution, source du classement
  tools/
    build_dataset.py          construit data/v1 depuis tools/cases/ et contrôle chaque cas
    validate.py               validation du schéma, bibliothèque standard
    check_contamination.py    recouvrement entre les cas et un corpus d'entraînement
    leaderboard.py            tableau du classement depuis results/
    make_croissant.py         régénère data/croissant.json
    cases/                    sources des cas (sorties réelles et générateurs synthétiques)
```

### Format d'un cas

Un objet JSON par ligne, voir l'exemple et les champs dans le [README anglais](README.md#case-format)
et le contrat complet dans [data/v1/schema.json](data/v1/schema.json). Les cas `qa`
remplacent `cmd`, `exit`, `duration` et `output` par un `history` (liste de
`{cmd, exit, output}`) et une `question`.

## Barème

Le barème est la fonction `score_case` de [run.py](run.py). Il n'utilise aucun modèle et
donne le même nombre sur toutes les machines.

1. **Normaliser** la réponse : minuscules, accents retirés, apostrophes typographiques
   remplacées, espaces horizontaux fusionnés. Les motifs sont écrits pour cette forme :
   `echec` reconnaît « Échec » et `8[.,]9` reconnaît « 8.9 » et « 8,9 ».
2. **Interdits :** si un motif global ([scoring.json](data/v1/scoring.json) : balises et
   formules de raisonnement, markdown, adresses MAC) ou un motif du cas (boucle locale, IPv6
   de lien local, tmpfs, processeur inventé, mauvais compte, version inventée) apparaît, le
   cas vaut 0.
3. **Faits :** sinon le score est la part des motifs `expected` trouvés.
4. **Longueur :** une réponse au-delà de `max_words` (20 pour un résumé, 30 pour une
   question) est multipliée par 0,8.

Le score du benchmark est la moyenne des cas, en %. Chaque réponse de référence vaut
100 %, et chaque nombre qu'elle cite figure dans l'entrée du modèle ; les tests le vérifient.

### Juge LLM optionnel

Les regex vérifient que les faits sont là ; elles ne prouvent pas que rien d'autre n'a été
inventé. `--judge-base-url` et `--judge-model` demandent à un second modèle, avec le prompt
publié dans [prompts.json](data/v1/prompts.json) (`judge`), si chaque réponse contient une
affirmation non étayée. Le taux du juge est stocké et affiché dans sa propre colonne, jamais
mêlé au score, et dépend du modèle juge : indiquez toujours lequel. Un petit juge n'est pas
fiable ; prenez le modèle le plus solide possible.

## Protocole

- **Entrée.** Pour chaque cas, le lanceur construit un prompt système et un message
  utilisateur depuis [prompts.json](data/v1/prompts.json) : commande, statut (succès ou
  échec avec code), durée, nombre de lignes affichées, puis la sortie. Au-delà de 3 500
  caractères, la sortie garde ses premiers 35 % et ses derniers 65 %, le milieu remplacé
  par `[... N lignes omises ...]`. Chaque entrée d'historique est coupée à 1 200 caractères.
- **Décodage.** Complétion de chat en flux, température 0, graine 0, `max_tokens` 96 pour
  un résumé et 128 pour une question. `chat_template_kwargs.enable_thinking=false` est
  envoyé pour que les modèles à raisonnement hybride répondent directement
  (`--allow-thinking` pour les mesurer en réflexion ; le raisonnement compte alors dans le
  TTFT).
- **Préchauffage.** Une requête courte avant le premier cas, non mesurée, pour ne pas
  compter le chargement du modèle. Les cas passent ensuite un par un, dans l'ordre du
  fichier, comme une vraie session.
- **Ce qui est chronométré.** Le TTFT est le délai jusqu'au premier caractère non blanc du
  contenu de la réponse. Les deltas de raisonnement (`reasoning_content`) sont exclus de la
  réponse, donc un modèle qui réfléchit d'abord le paie.
- **Métadonnées.** Le résultat enregistre la version du benchmark et des données, le
  SHA-256 des fichiers de cas et de configuration, les réglages de décodage, le moteur
  (détecté par `/props`, `/api/version`, `/version` ou `/v1/models`) et le matériel
  (processeur, threads, RAM, GPU, système), remplis automatiquement quand le serveur tourne
  sur la même machine. Ni nom d'hôte ni chemin de modèle ne sont enregistrés.

## Lancer

Python 3.9 ou plus, aucune dépendance. Démarrer un serveur compatible OpenAI, puis :

```sh
# llama.cpp
llama-server -m modele.gguf --port 8080 -c 8192 -ngl 99 --jinja
python3 benchmark/run.py --base-url http://127.0.0.1:8080/v1 --model mon-modele --lang all --split test

# Ollama
python3 benchmark/run.py --base-url http://127.0.0.1:11434/v1 --model qwen3:1.7b --lang all

# LM Studio
python3 benchmark/run.py --base-url http://127.0.0.1:1234/v1 --model qwen3-1.7b --lang all

# vLLM
vllm serve Qwen/Qwen3-1.7B --port 8000
python3 benchmark/run.py --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-1.7B --lang all
```

Options utiles : `--lang`, `--split`, `--label`, `--limit`, `--hardware` (obligatoire pour
un serveur distant), `--notes`, `--extra-body`, `--judge-base-url` et `--judge-model`,
`--reference` (note les réponses de référence, sans serveur : 100 attendu), `--rescore`.
Le détail est dans le [README anglais](README.md#run-it).

Le lanceur affiche un tableau par catégorie et écrit
`results/<date UTC>_<label>_<lang>_<split>.json` avec chaque réponse, son score et ses temps.

## Classement

Split `test`, mesuré avec ce lanceur. Une cellule vide n'a pas été mesurée.

<!-- leaderboard:start -->
| Model | Lang | Score | Fact recall | Forbidden hit | Judge: hallucinated | TTFT median (s) | TTFT p90 (s) | tok/s | Backend | Hardware | Result file |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| gemma-4-e2b-it-q4_0 | en | 75.1 | 74.7 | 0.0 % |  | 0.347 | 1.702 | 64.5 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-053942_gemma-4-e2b-it-q4-0_en_test.json](results/20260927-053942_gemma-4-e2b-it-q4-0_en_test.json) |
| qwen3.5-2b-q4_k_m | en | 69.1 | 73.0 | 4.8 % |  | 0.281 | 1.196 | 73.0 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-053712_qwen3.5-2b-q4-k-m_en_test.json](results/20260927-053712_qwen3.5-2b-q4-k-m_en_test.json) |
| steph-qwen3.5-0.8b-fixed-q4_k_m | en | 59.4 | 62.9 | 6.5 % |  | 0.127 | 0.556 | 128.5 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-151005_steph-qwen3.5-0.8b-fixed-q4-k-m_en_test.json](results/20260927-151005_steph-qwen3.5-0.8b-fixed-q4-k-m_en_test.json) |
| qwen3.5-0.8b-q4_k_m | en | 49.5 | 53.9 | 3.2 % |  | 0.131 | 0.554 | 125.8 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-053438_qwen3.5-0.8b-q4-k-m_en_test.json](results/20260927-053438_qwen3.5-0.8b-q4-k-m_en_test.json) |
| steph-granite4.0h-350m-soup-uniform-q4_k_m | en | 43.6 | 46.1 | 4.8 % |  | 0.113 | 0.447 | 145.0 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-150730_steph-granite4.0h-350m-soup-uniform-q4-k-m_en_test.json](results/20260927-150730_steph-granite4.0h-350m-soup-uniform-q4-k-m_en_test.json) |
| steph-gemma3-270m-s42-judged-q8_0 | en | 33.5 | 34.3 | 3.2 % |  | 0.042 | 0.138 | 234.9 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-150856_steph-gemma3-270m-s42-judged-q8-0_en_test.json](results/20260927-150856_steph-gemma3-270m-s42-judged-q8-0_en_test.json) |
| lfm2.5-1.2b-instruct-q4_k_m | en | 30.6 | 31.5 | 1.6 % |  | 0.246 | 0.815 | 143.3 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-053533_lfm2.5-1.2b-instruct-q4-k-m_en_test.json](results/20260927-053533_lfm2.5-1.2b-instruct-q4-k-m_en_test.json) |
| gemma-4-e2b-it-q4_0 | fr | 73.8 | 74.7 | 0.0 % |  | 0.367 | 1.731 | 67.4 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-054048_gemma-4-e2b-it-q4-0_fr_test.json](results/20260927-054048_gemma-4-e2b-it-q4-0_fr_test.json) |
| qwen3.5-2b-q4_k_m | fr | 62.2 | 68.5 | 4.8 % |  | 0.281 | 1.201 | 74.0 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-053824_qwen3.5-2b-q4-k-m_fr_test.json](results/20260927-053824_qwen3.5-2b-q4-k-m_fr_test.json) |
| steph-qwen3.5-0.8b-fixed-q4_k_m | fr | 59.4 | 62.4 | 6.5 % |  | 0.137 | 0.565 | 129.5 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-151031_steph-qwen3.5-0.8b-fixed-q4-k-m_fr_test.json](results/20260927-151031_steph-qwen3.5-0.8b-fixed-q4-k-m_fr_test.json) |
| qwen3.5-0.8b-q4_k_m | fr | 49.7 | 51.1 | 1.6 % |  | 0.13 | 0.561 | 132.2 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-053504_qwen3.5-0.8b-q4-k-m_fr_test.json](results/20260927-053504_qwen3.5-0.8b-q4-k-m_fr_test.json) |
| steph-granite4.0h-350m-soup-uniform-q4_k_m | fr | 49.4 | 54.5 | 6.5 % |  | 0.116 | 0.451 | 145.3 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-150750_steph-granite4.0h-350m-soup-uniform-q4-k-m_fr_test.json](results/20260927-150750_steph-granite4.0h-350m-soup-uniform-q4-k-m_fr_test.json) |
| steph-gemma3-270m-s42-judged-q8_0 | fr | 47.3 | 50.6 | 4.8 % |  | 0.043 | 0.142 | 234.4 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-150907_steph-gemma3-270m-s42-judged-q8-0_fr_test.json](results/20260927-150907_steph-gemma3-270m-s42-judged-q8-0_fr_test.json) |
| lfm2.5-1.2b-instruct-q4_k_m | fr | 36.2 | 36.5 | 1.6 % |  | 0.262 | 0.815 | 142.6 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-053607_lfm2.5-1.2b-instruct-q4-k-m_fr_test.json](results/20260927-053607_lfm2.5-1.2b-instruct-q4-k-m_fr_test.json) |
<!-- leaderboard:end -->

Les lignes `steph-*` sont les candidats affinés maison de steph (LoRA, entraînés uniquement
sur des données françaises), passés ici avec exactement le même protocole que les modèles
bruts au-dessus, pour une comparaison directe.

[`resolve()`](../src/steph/digest.py) (le raccourci déterministe de steph, à base de règles,
français uniquement, sans appel à un LLM) est scoré à part et n'apparaît pas dans ce
tableau : ce n'est pas un modèle, et ses règles ont été étendues en regardant le split
`test` de ce banc, donc un score sur `test` serait optimiste et non comparable aux lignes
ci-dessus. Il est scoré seulement sur `dev` : en 50,1, fr 60,2 (cas de tâche `summary`
seulement, n=39 par langue ; les 4 cas `history-qa` demandent un historique de conversation
qu'il ne voit jamais, et sont exclus plutôt que notés en échec) ; voir
[`results/20260927-151930_steph-resolve_fr_dev.json`](results/20260927-151930_steph-resolve_fr_dev.json)
et le fichier `en` à côté.

## Protocole steph (prompt d'entraînement), non comparable au classement standard

Les modèles affinés de steph ont appris un prompt système court, en français
([`train_system_prompt.txt`](../bench/matrix/finetune/train_system_prompt.txt), `TRAIN_SYSTEM`
dans [`label.py`](../bench/matrix/finetune/label.py)), pas celui, plus long, de Steph Speak Bench
(`data/v1/prompts.json`, 824 caractères). Les lignes ci-dessous repassent les 3 mêmes
modèles affinés sur le même split `test` avec leur propre prompt d'entraînement, via
`run.py --system-prompt-file` ; le fichier utilisé et son texte exact sont enregistrés dans
`protocol.system_prompt_file` et `protocol.system_prompt_override` de chaque résultat.
C'est un protocole différent, pas un modèle meilleur ou pire : **ne pas comparer ces scores
au tableau ci-dessus**, seulement entre eux et à la ligne standard du même modèle.

<!-- steph-protocol:start -->
| Model | Lang | Score | Fact recall | Forbidden hit | Judge: hallucinated | TTFT median (s) | TTFT p90 (s) | tok/s | Backend | Hardware | Result file |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| steph-qwen3.5-0.8b-fixed-q4_k_m-steph-protocol | en | 55.8 | 56.2 | 3.2 % |  | 0.13 | 0.532 | 133.1 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-153046_steph-qwen3.5-0.8b-fixed-q4-k-m-steph-protocol_en_test.json](results/steph-protocol/20260927-153046_steph-qwen3.5-0.8b-fixed-q4-k-m-steph-protocol_en_test.json) |
| steph-granite4.0h-350m-soup-uniform-q4_k_m-steph-protocol | en | 44.5 | 44.4 | 1.6 % |  | 0.114 | 0.427 | 146.4 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-152840_steph-granite4.0h-350m-soup-uniform-q4-k-m-steph-protocol_en_test.json](results/steph-protocol/20260927-152840_steph-granite4.0h-350m-soup-uniform-q4-k-m-steph-protocol_en_test.json) |
| steph-gemma3-270m-s42-judged-q8_0-steph-protocol | en | 29.5 | 28.1 | 1.6 % |  | 0.038 | 0.148 | 229.8 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-152945_steph-gemma3-270m-s42-judged-q8-0-steph-protocol_en_test.json](results/steph-protocol/20260927-152945_steph-gemma3-270m-s42-judged-q8-0-steph-protocol_en_test.json) |
| steph-qwen3.5-0.8b-fixed-q4_k_m-steph-protocol | fr | 62.4 | 64.0 | 3.2 % |  | 0.136 | 0.541 | 131.6 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-153109_steph-qwen3.5-0.8b-fixed-q4-k-m-steph-protocol_fr_test.json](results/steph-protocol/20260927-153109_steph-qwen3.5-0.8b-fixed-q4-k-m-steph-protocol_fr_test.json) |
| steph-granite4.0h-350m-soup-uniform-q4_k_m-steph-protocol | fr | 51.6 | 53.9 | 3.2 % |  | 0.121 | 0.437 | 146.8 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-152901_steph-granite4.0h-350m-soup-uniform-q4-k-m-steph-protocol_fr_test.json](results/steph-protocol/20260927-152901_steph-granite4.0h-350m-soup-uniform-q4-k-m-steph-protocol_fr_test.json) |
| steph-gemma3-270m-s42-judged-q8_0-steph-protocol | fr | 51.6 | 54.5 | 3.2 % |  | 0.04 | 0.147 | 235.4 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-152956_steph-gemma3-270m-s42-judged-q8-0-steph-protocol_fr_test.json](results/steph-protocol/20260927-152956_steph-gemma3-270m-s42-judged-q8-0-steph-protocol_fr_test.json) |
<!-- steph-protocol:end -->

## Banc multilingue, modèles bruts seulement

Étape multilingue de la mission d'affinage de steph (le journal de mission interne (non publié),
`docs/research-terminal-languages.md`) : quatre langues de plus, allemand, espagnol, portugais et russe,
ajoutées aux 105 cas existants sous le même identifiant. Cette section porte **seulement sur les modèles
bruts** (aucun modèle affiné steph n'a encore été entraîné ni évalué dans ces langues ; ce sera fait après
le prochain réentraînement).

- **Ce qui change par langue.** Pour chaque cas, `question`, `expected`, `forbidden` et `reference` sont
  traduits : c'est ce qui teste si un modèle répond vraiment dans la langue demandée. La plupart des
  `output` restent en anglais ou en français, inchangés : d'après `docs/research-terminal-languages.md`,
  presque aucun outil en ligne de commande ne traduit ses messages quelle que soit la locale, donc rien ne
  justifie d'inventer une sortie qu'une vraie machine allemande ou russe ne produirait jamais.
- **Captures réelles dans les nouvelles langues.** Quelques cas (`git-status-untracked`,
  `pkg-apt-upgrade`, `disk-df-workstation`, `disk-du-projects`, `list-ls-etc`) ont reçu une vraie capture
  sur une machine de test Debian, avec le catalogue gettext propre à l'outil (`LANGUAGE=de`/`es`/`pt`/`ru`
  sur une locale de base française, la locale complète n'ayant pas pu être installée) ; voir le champ
  `notes` de chaque cas pour la méthode exacte et ses limites (le format des dates et des nombres reste
  celui de la locale de base). `pkg-apt-lock` et `net-ping-local` n'ont pas pu être reproduits sans risque
  ou pas du tout et gardent une sortie de repli en anglais ; leurs faits attendus et leur référence restent
  traduits.
- **Motifs de score et normalisation.** Les trémas allemands (ü/ö/ä), les accents espagnols/portugais et
  ñ/ç, et le й/ё russe perdent tous leur diacritique sous la même normalisation NFKD qui retire déjà les
  accents français ; les motifs expected/forbidden sont écrits sous cette forme dépouillée (voir
  `run.normalize`).

<!-- multilingual-leaderboard:start -->
| Model | Lang | Score | Fact recall | Forbidden hit | Judge: hallucinated | TTFT median (s) | TTFT p90 (s) | tok/s | Backend | Hardware | Result file |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| gemma-4-e2b-it-q4_0 | de | 71.3 | 70.2 | 0.0 % |  | 0.35 | 1.722 | 65.7 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-174024_gemma-4-e2b-it-q4-0_de_test.json](results/multilingual/20260927-174024_gemma-4-e2b-it-q4-0_de_test.json) |
| qwen3.5-2b-q4_k_m | de | 65.9 | 69.7 | 1.6 % |  | 0.279 | 1.205 | 75.3 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-173241_qwen3.5-2b-q4-k-m_de_test.json](results/multilingual/20260927-173241_qwen3.5-2b-q4-k-m_de_test.json) |
| qwen3.5-0.8b-q4_k_m | de | 42.0 | 43.8 | 3.2 % |  | 0.133 | 0.575 | 128.5 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-172850_qwen3.5-0.8b-q4-k-m_de_test.json](results/multilingual/20260927-172850_qwen3.5-0.8b-q4-k-m_de_test.json) |
| lfm2.5-1.2b-instruct-q4_k_m | de | 25.7 | 25.8 | 1.6 % |  | 0.212 | 0.777 | 145.1 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-173719_lfm2.5-1.2b-instruct-q4-k-m_de_test.json](results/multilingual/20260927-173719_lfm2.5-1.2b-instruct-q4-k-m_de_test.json) |
| gemma-4-e2b-it-q4_0 | es | 70.3 | 68.5 | 0.0 % |  | 0.348 | 1.748 | 66.0 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-174129_gemma-4-e2b-it-q4-0_es_test.json](results/multilingual/20260927-174129_gemma-4-e2b-it-q4-0_es_test.json) |
| qwen3.5-2b-q4_k_m | es | 63.7 | 66.9 | 1.6 % |  | 0.279 | 1.217 | 74.5 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-173345_qwen3.5-2b-q4-k-m_es_test.json](results/multilingual/20260927-173345_qwen3.5-2b-q4-k-m_es_test.json) |
| qwen3.5-0.8b-q4_k_m | es | 49.9 | 54.5 | 6.5 % |  | 0.13 | 0.59 | 129.8 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-172921_qwen3.5-0.8b-q4-k-m_es_test.json](results/multilingual/20260927-172921_qwen3.5-0.8b-q4-k-m_es_test.json) |
| lfm2.5-1.2b-instruct-q4_k_m | es | 39.2 | 41.0 | 6.5 % |  | 0.26 | 0.816 | 142.5 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-173753_lfm2.5-1.2b-instruct-q4-k-m_es_test.json](results/multilingual/20260927-173753_lfm2.5-1.2b-instruct-q4-k-m_es_test.json) |
| gemma-4-e2b-it-q4_0 | pt | 68.3 | 67.4 | 1.6 % |  | 0.354 | 1.741 | 65.5 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-174234_gemma-4-e2b-it-q4-0_pt_test.json](results/multilingual/20260927-174234_gemma-4-e2b-it-q4-0_pt_test.json) |
| qwen3.5-2b-q4_k_m | pt | 61.3 | 63.5 | 0.0 % |  | 0.332 | 1.719 | 73.9 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-173458_qwen3.5-2b-q4-k-m_pt_test.json](results/multilingual/20260927-173458_qwen3.5-2b-q4-k-m_pt_test.json) |
| qwen3.5-0.8b-q4_k_m | pt | 44.0 | 45.5 | 1.6 % |  | 0.153 | 1.609 | 128.8 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-173003_qwen3.5-0.8b-q4-k-m_pt_test.json](results/multilingual/20260927-173003_qwen3.5-0.8b-q4-k-m_pt_test.json) |
| lfm2.5-1.2b-instruct-q4_k_m | pt | 31.0 | 29.8 | 1.6 % |  | 0.246 | 0.818 | 141.7 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-173822_lfm2.5-1.2b-instruct-q4-k-m_pt_test.json](results/multilingual/20260927-173822_lfm2.5-1.2b-instruct-q4-k-m_pt_test.json) |
| gemma-4-e2b-it-q4_0 | ru | 73.5 | 75.8 | 3.2 % |  | 0.37 | 1.73 | 63.5 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-174352_gemma-4-e2b-it-q4-0_ru_test.json](results/multilingual/20260927-174352_gemma-4-e2b-it-q4-0_ru_test.json) |
| qwen3.5-2b-q4_k_m | ru | 66.7 | 72.5 | 4.8 % |  | 0.64 | 1.739 | 73.0 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-173641_qwen3.5-2b-q4-k-m_ru_test.json](results/multilingual/20260927-173641_qwen3.5-2b-q4-k-m_ru_test.json) |
| qwen3.5-0.8b-q4_k_m | ru | 45.0 | 48.9 | 4.8 % |  | 0.46 | 1.111 | 130.7 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-173056_qwen3.5-0.8b-q4-k-m_ru_test.json](results/multilingual/20260927-173056_qwen3.5-0.8b-q4-k-m_ru_test.json) |
| lfm2.5-1.2b-instruct-q4_k_m | ru | 33.3 | 36.0 | 3.2 % |  | 0.266 | 0.839 | 139.7 | llama.cpp b11146-7fe450e19 | Apple M3 Pro, 18 GB | [20260927-173903_lfm2.5-1.2b-instruct-q4-k-m_ru_test.json](results/multilingual/20260927-173903_lfm2.5-1.2b-instruct-q4-k-m_ru_test.json) |
<!-- multilingual-leaderboard:end -->

## Soumettre un résultat

1. Lancer le split `test` dans les deux langues avec un `data/v1` non modifié (le résultat
   enregistre ses sommes de contrôle).
2. Garder le protocole par défaut, ou dire ce qui change dans `--notes` (un prompt modifié
   est un autre benchmark, pas un résultat).
3. Ouvrir une pull request qui ajoute vos fichiers `results/*.json`. Pour un serveur
   distant, passer `--hardware`. Lancer `python3 benchmark/tools/leaderboard.py --update-readme`
   pour rafraîchir le tableau.
4. Ne jamais régler sur `test`. Régler sur `dev`.

## Contamination

Le split test ne contient que des cas synthétiques écrits pour ce benchmark, jamais de
sorties réelles des machines où le corpus d'affinage de steph a été collecté.
[tools/check_contamination.py](tools/check_contamination.py) compare chaque cas test à un
corpus d'entraînement : sortie identique, part de lignes identiques, part de lignes
identiques une fois les chiffres masqués, part de 8-grammes de mots communs. Il a été lancé
contre le corpus d'affinage de steph avant publication ; le résultat figure ci-dessous. Le
split test n'a jamais servi à entraîner ni à régler steph.

<!-- contamination:start -->
Lancé le 2026-09-27 contre le corpus d'affinage de steph (7 fichiers JSON Lines, 21 336 textes), split `test`, deux langues :

| Verdict | Cas |
|---|---:|
| propre | 119 |
| suspect (lignes quasi identiques une fois les chiffres masqués, sans 8-grammes communs au-delà du seuil) | 5 |
| contaminé | 0 |

Trois cas matériel qui recoupaient le corpus (`hw-lscpu`, `hw-lsusb`, `hw-system-profiler-macos`) ont été déplacés en `dev` avant publication. Les suspects sont des en-têtes de `ping` et `vm_stat` et une mise en page de `sensors`, dont le libellé fixe est commun à toute capture du même outil.
<!-- contamination:end -->

Chaque cas porte aussi une chaîne canari. Si vous constituez un corpus d'entraînement,
écartez tout document qui contient `termspeak-canary-v1-5e0c83a1d7f2`. Un modèle qui la
reproduit a vu le benchmark.

## Anonymisation

Les sorties réelles ont été anonymisées à la main : noms d'utilisateur, d'hôte et de projet
remplacés, adresses du réseau local et du VPN déplacées vers des plages privées ou de
documentation, adresses MAC, UUID, numéros de série et identifiants d'interface IPv6
retirés. Chaque cas passe un scanner automatique (plages IP, MAC, UUID, empreintes,
e-mails, chemins personnels, jetons, domaines privés et liste privée de noms connus) avec
zéro trouvaille ; les tests l'imposent.

## Standards suivis

| Standard | Où |
|---|---|
| Datasheets for Datasets (Gebru et al.) | [data/README.md](data/README.md) |
| Métadonnées de fiche Hugging Face | en-tête YAML de [data/README.md](data/README.md) |
| MLCommons Croissant 1.0 avec Responsible AI 1.0 | [data/croissant.json](data/croissant.json) |
| JSON Schema 2020-12 | [data/v1/schema.json](data/v1/schema.json) |
| Citation File Format 1.2 | [CITATION.cff](CITATION.cff) |
| Chaîne canari (convention BIG-bench) | champ `canary` de chaque cas |
| Données versionnées et immuables | `data/v1/` ; une correction sort en `v2` |

## Limites

- Une centaine de cas par langue : assez pour classer des modèles éloignés, pas pour
  départager deux modèles à quelques points près. Publiez le tableau par catégorie, pas
  seulement la moyenne.
- Le barème par regex récompense les faits énoncés. Il peut rater une paraphrase correcte
  et ne voit pas une invention subtile qu'aucun motif interdit n'anticipe ; le juge
  optionnel en couvre une partie.
- Le choix d'outils suit un usage de développeur et de serveur domestique sous Linux et
  macOS. Les shells Windows ne sont pas couverts.
- Les réponses de référence reflètent une idée du résumé parlé utile : télégraphique, les
  faits d'abord, 15 mots au plus.

## Licences

| Partie | Licence |
|---|---|
| Cas, faits attendus, références, prompts, barème, résultats (`data/`, `results/`) | [CC BY 4.0](LICENSE-DATA) |
| Scripts (`run.py`, `tools/`, `tests/test_benchmark.py`) | [MIT](LICENSE-CODE) |
| Le reste du dépôt steph | PolyForm Noncommercial 1.0.0, voir [LICENSE.md](../LICENSE.md) |

Le dossier du benchmark est volontairement sous licences permissives pour être réutilisé,
y compris commercialement. **Le reste du dépôt steph ne l'est pas** : le terminal parlant
reste sous PolyForm Noncommercial.

## Citation

Voir [CITATION.cff](CITATION.cff) et l'entrée BibTeX du [README anglais](README.md#citation).
