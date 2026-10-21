# Brouillon de carte de jeu de données : steph-speak-train

Brouillon rédigé pendant l'audit de publication (voir le journal de mission interne (non publié)).
Brouillon seulement : aucune création de dépôt Hugging Face, aucun téléversement.
Décisions reprises de `docs/open-source.md` : licence **CC BY 4.0**, dépôt prévu
`lsmdx/steph-speak-train`, configurations `sft` et `dpo`, splits `train`/`validation`,
jeu complet (pas d'échantillon).

**Toute taille, tout compte ci-dessous vient d'une exécution réelle du script
d'assemblage sur le corpus du 2026-09-27, avant le réentraînement final (pas encore
fait).** Le jeu publié sera celui reconstruit après ce réentraînement (dernier prompt,
dernier gabarit, dernier corpus) : les tailles par tâche et par langue peuvent encore
changer, la structure (configurations, champs, licence) non.

## En-tête YAML (Hugging Face)

```yaml
license: cc-by-4.0
pretty_name: steph-speak-train
language:
  - fr
  - en
multilinguality: multilingual
size_categories:
  - 1K<n<10K
task_categories:
  - summarization
  - conversational
tags:
  - accessibility
  - screen-reader
  - terminal
  - fine-tuning
  - steph
configs:
  - config_name: sft
    data_files:
      - split: train
        path: sft/train.jsonl
      - split: validation
        path: sft/validation.jsonl
  - config_name: dpo
    data_files:
      - split: train
        path: dpo/train.jsonl
      - split: validation
        path: dpo/validation.jsonl
```

## Corps de la carte

### Description

Jeu d'entraînement du modèle affiné [steph-speak](model-card-draft.md) : paires
entrée/sortie pour apprendre à un petit modèle de langage à résumer à voix haute la
sortie d'une commande de terminal, pour une personne aveugle ou malvoyante. Deux
configurations Hugging Face Datasets :

- **`sft`** : paires `messages` (format chat, système/utilisateur/assistant), pour
  l'affinage supervisé.
- **`dpo`** : triplets `prompt`/`chosen`/`rejected`, pour l'affinage par préférence
  anti-invention. **Vide dans ce brouillon** : les rejets viennent de la sortie
  d'un modèle déjà affiné en SFT jugée inventive, donc du round d'entraînement lui-même,
  pas de l'assemblage du corpus brut. Peuplé au réentraînement final.

Carte de modèle réciproque : [model-card-draft.md](model-card-draft.md) (référence ce
jeu dans son champ `datasets`).

### Usage prévu

Affinage LoRA (SFT puis DPO) d'un petit modèle de langage (voir
`docs/model-card-draft.md`, section « Recette d'entraînement ») pour le résumé vocal de
sorties de terminal dans [steph](https://github.com/tutozz/steph) (licence PolyForm
Noncommercial, non couverte par cette carte : seules les données le sont).

### Usages hors périmètre

- Entraînement d'un assistant généraliste : le jeu ne couvre qu'un registre étroit
  (commandes de terminal Linux/macOS, style télégraphique, faits exacts sans
  reformulation).
- Évaluation de modèle : ce jeu sert à l'entraînement, pas au score. Utiliser
  [Steph Speak Bench](https://github.com/tutozz/steph/tree/master/benchmark)
  (`lsmdx/steph-speak-bench`) pour l'évaluation ; aucune ligne du banc n'entre dans ce
  jeu (voir Contamination).

## Datasheet

Sections d'après *Datasheets for Datasets* (Gebru et al., 2021), même grille que
`benchmark/data/README.md`.

### Motivation

- **Objet.** Apprendre à un petit modèle affiné à transformer une sortie de commande de
  terminal en une phrase courte dite à voix haute, sans invention, pour une personne
  aveugle ou malvoyante.
- **Créateur.** Luis Parra, auteur de steph. Aucun financement externe.

### Composition

Une instance = un tour utilisateur (commande, statut, durée, sortie ou historique de
session) et la réponse de référence, au format chat `messages` (`sft`) ou
`prompt`/`chosen`/`rejected` (`dpo`).

<!-- dataset-stats:start -->
Mesuré le 2026-09-27 sur RTX 3060 (`build_dataset_release.py`, avant le réentraînement final) :

| Configuration | train | validation | total |
|---|---:|---:|---:|
| `sft` | 2 457 | 136 | **2 593** |
| `dpo` | 0 | 0 | 0 (peuplé au réentraînement final, voir « Usage prévu ») |

`sft` par tâche :

| Tâche | Lignes | Description |
|---|---:|---|
| `summary` | 1 396 | résumé vocal d'une sortie de commande (tâche principale de steph) |
| `detail` | 529 | détail de la dernière commande, sur demande |
| `start` | 338 | annonce du début d'une commande longue |
| `progress` | 140 | progression d'une commande longue en cours |
| `qa` | 173 | question sur l'historique de la session (sessions synthétiques, voir Collecte) |
| `summary_residual` | 5 | résidu du résumé (cas rares hors catégorie) |
| `flux` | 12 | journal en continu filtré (nouvelles erreurs/avertissements) |

`sft` par langue : français 2 117, anglais 476 (le français couvre les 7 tâches ;
l'anglais couvre `summary` seulement, capté séparément sous locale anglaise, voir
le journal de mission interne (non publié)).

`sft` par source neutre (nom de catégorie, jamais un nom de machine réel) :

| Source | Langue | Tâche | Lignes |
|---|---|---|---:|
| `linux-dev` | fr | summary | 230 |
| `linux-low` | fr | summary | 201 |
| `linux-low.en` | en | summary | 220 |
| `macos` | fr | summary | 119 |
| `macos.en` | en | summary | 256 |
| `snapshot-linux-dev` | fr | summary | 150 |
| `snapshot-linux-low` | fr | summary | 220 |
| `detail` | fr | detail | 529 |
| `start` | fr | start | 338 |
| `progress` | fr | progress | 140 |
| `flux` | fr | flux | 12 |
| `summary_residual` | fr | summary_residual | 5 |
| `qa-synth` | fr | qa | 173 |
<!-- dataset-stats:end -->

- **Champs (`sft`).** `messages` (liste `{role, content}`, système/utilisateur/assistant
  ou système/utilisateur/assistant/utilisateur/assistant pour `qa`), `language` (`fr` ou
  `en`), `task` (`summary`, `detail`, `start`, `progress`, `flux`, `summary_residual`,
  `qa`), `source` (catégorie neutre, jamais un nom de machine réel), `provenance`
  (`real_capture` ou `synthetic_session`), `labeler` (toujours `qwen3.5-9b`), `judge`
  (toujours `qwen3.5-9b-2pass`), `resynced` (booléen : `true` si la ligne a été
  reconstruite avec le code de digest actuel à partir de la capture brute — voir
  Prétraitement — `false` si elle vient telle quelle du corpus finalisé, faute de
  capture brute encore disponible pour la reconstruire, cas des lignes `snapshot-*` et de
  toutes les tâches `detail`/`start`/`progress`/`flux`/`summary_residual`/`qa`, déjà au
  format court de production).
- **Champs (`dpo`).** `prompt` (système/utilisateur), `chosen` (réponse ancrée retenue),
  `rejected` (réponse d'un modèle déjà affiné, jugée inventive), plus les mêmes champs de
  documentation que `sft`.
- **Étiquettes.** Réponse de référence produite par l'enseignant `Qwen/Qwen3.5-9B`
  (température 0), filtrée par un juge deux passes du même modèle (accord des deux passes
  requis pour rejeter, voir Prétraitement).
- **Manquant.** Aucun ; chaque ligne a les huit champs `sft` ou les sept champs `dpo`.
- **Données confidentielles ou personnelles.** Aucune à notre connaissance : voir la
  section Anonymisation. Deux audits indépendants à 0 trouvaille de haute confiance sur
  ce jeu exact (détail ci-dessous) ; « à notre connaissance » reste la formule correcte,
  aucun audit automatisé ne garantit une absence totale.
- **Contenu choquant.** Aucun (sorties de terminal techniques uniquement).

### Collecte

- **Captures réelles** (`provenance: real_capture`, tâches `summary`, `detail`, `start`,
  `progress`, `flux`, `summary_residual`). Sorties réelles de commandes exécutées sur les
  machines de développement et de test de l'auteur (Linux, macOS), en français et, pour
  `summary` seulement, sous locale anglaise (`LANG=C`/`en_US`). `detail`, `start`,
  `progress`, `flux` et `summary_residual` réutilisent les mêmes captures réelles,
  reformatées au gabarit exact de chaque fonctionnalité (`build_feature_corpus.py`) :
  aucun texte inventé pour l'entrée.
- **Sessions synthétiques** (`provenance: synthetic_session`, tâche `qa`). Sessions de
  questions/réponses composées à partir du même corpus réel (`qa_corpus.py`) : l'agencement
  multi-tour est synthétique, mais commandes et sorties viennent des mêmes captures
  réelles, jamais inventées.
- **Période.** 2026.
- **Anonymisation avant capture.** Noms d'utilisateur, d'hôte et de projet remplacés ;
  réseau LAN/VPN et adresses publiques remappés vers des plages privées ou de
  documentation ; adresses MAC neutralisées ; UUID, numéros de série et identifiants
  d'interface IPv6 retirés (même politique que `benchmark/data/README.md`).

### Prétraitement, nettoyage, étiquetage

1. Capture (`capture_corpus.py`) puis anonymisation (`clean_pii.py`, audit
   `audit_pii.py`).
2. Étiquetage par l'enseignant `Qwen/Qwen3.5-9B` (`label.py`, `label_features.py`,
   `qa_corpus.py`) : température 0, système d'entraînement court par tâche.
3. Filtrage par un juge deux passes du même modèle (`judge_corpus_2pass.py`,
   `judge_lib.py`) : rejet seulement si les deux passes s'accordent sur une invention.
4. Finalisation (`finalize_labels.py`) : re-scan PII, nom de source neutre par machine,
   concaténation.
5. Assemblage publiable (`bench/matrix/finetune/build_dataset_release.py`, ce jeu) :
   même composition que `compose_train.py` (doublons exacts retirés, rejets du juge
   retirés — y compris les rejets du détail, réappliqués ici pour la première fois,
   voir le journal de mission interne (non publié) —, lignes `snapshot-*` plafonnées par
   programme). Pour la tâche `summary` avec une capture brute encore disponible, le tour
   utilisateur est reconstruit avec le code actuel de `steph.digest`/`steph.prompts`
   (même intention que `rebuild_p15.py`, mais qui suit la langue de chaque ligne au lieu
   de supposer le français) et toute étiquette qui ne s'ancre plus dans cette entrée
   reconstruite est écartée (vérifié contre `steph.grounding`). Les lignes `summary` sans
   capture brute disponible (`snapshot-*`) et toutes les lignes `detail`/`start`/
   `progress`/`flux`/`summary_residual`/`qa` sont gardées telles que finalisées : leur
   contrat autorise l'inférence (cause, connaissance générale d'une commande) qu'une
   vérification d'ancrage littérale, calibrée pour `summary`, rejetterait à tort — mesuré
   sur ce jeu : appliquer cette vérification à `detail` en écartait 77 %, loin au-dessus
   du taux d'invention réel de 26 % déjà mesuré par le juge ; ces tâches restent
   protégées par leur propre juge deux passes, pas par ce filtre-ci.
6. Contrôle anti-contamination : le script refuse d'écrire si une ligne contient le
   canari du banc `termspeak-canary-v1-5e0c83a1d7f2` (0 trouvaille sur cette exécution).

### Usages

- **Prévu.** Affinage LoRA (SFT, puis DPO une fois `dpo` peuplé au réentraînement final)
  du modèle `steph-speak`.
- **Non prévu.** Évaluation de modèle (utiliser Steph Speak Bench) ; entraînement d'un
  assistant généraliste hors résumé de terminal.

### Distribution

- Licence **CC BY 4.0** pour les données (remplace le choix CC BY-NC 4.0 de la recherche
  initiale : décision utilisateur du 2026-09-27, voir `docs/open-source.md`).
  Scripts d'assemblage sous MIT (`SPDX-License-Identifier: MIT`, en-tête de
  `build_dataset_release.py`). Le reste du dépôt `steph` reste sous PolyForm
  Noncommercial et n'est pas couvert par ces licences.
- **Enseignant et juge : `Qwen/Qwen3.5-9B`, licence Apache 2.0.** Revérifiée directement
  le 2026-09-27 sur le fichier
  [`LICENSE` du dépôt exact `Qwen/Qwen3.5-9B`](https://huggingface.co/Qwen/Qwen3.5-9B/blob/main/LICENSE) :
  texte Apache 2.0 standard, titulaire du copyright Alibaba Cloud, aucune clause
  supplémentaire (ni Tongyi Qianwen, ni restriction sur la réutilisation des sorties ou
  sur l'entraînement d'un autre modèle à partir d'elles). Confirme, sur le dépôt exact
  cette fois et non plus seulement sur un modèle de la même famille, le constat de la
  recherche initiale (`docs/research-dataset-release.md`, section 3).
- Dépôt prévu : `lsmdx/steph-speak-train` (Hugging Face Datasets), toujours privé au
  2026-09-27.
- Métadonnées machine-lisibles : [`croissant.json`](../bench/matrix/finetune/croissant.json)
  (Croissant 1.0 + Responsible AI 1.0, brouillon : `contentUrl`/`sha256` de l'exécution de
  validation avant le réentraînement final, à régénérer).

### Anonymisation, PII

Deux audits indépendants, sur le jeu assemblé exact ci-dessus (2 593 lignes `sft`),
jamais sur des valeurs affichées :

| Audit | Portée | Trouvailles | Détail |
|---|---|---:|---|
| `audit_pii.py` (premier passage, déjà en place) | MAC, UUID, IP publiques/privées, e-mails, chemins `/home`/`/Users`, secrets, domaines privés, noms connus (liste hors dépôt) | voir le journal de mission interne (non publié), invariant « scanner à 0 avant tout » | appliqué en amont, à la finalisation (`finalize_labels.py`) et avant tout transfert |
| `audit_pii_second_pass.py` (second passage, nouveau) | noms propres capitalisés inconnus, hôtes dans un prompt shell capturé, e-mails obfusqués, formes de clé/jeton (GitHub, AWS, Slack, OpenAI, npm, JWT, clé publique SSH), numéros de série/IMEI, chemins home élargis, champs `hostnamectl` | 3 131 signalements bruts, tous classés faux positifs après relecture d'échantillon (détail ci-dessous) | `bench/matrix/finetune/audit_pii_second_pass.py`, exécuté sur RTX 3060 le 2026-09-27 |

Détail du second passage (comptes seulement, jamais une valeur) :

- `unknown_proper_noun` : 3 120 signalements sur 1 204 lignes (répartis sur les deux
  splits). Échantillon aléatoire de 50 relu à la main (graine fixe) : **0 nom propre
  réel**, uniquement du vocabulaire technique anglais en capitale médiane (« English »,
  « Query », « Module »…), des dates (« Sun Sep »), des chaînes matérielles/fournisseur
  (« Intel Corporation Sunrise »), des en-têtes de colonne (« Size Used ») et des mots
  français en début de proposition après une virgule ou deux-points. Un échantillon de
  50 sur 2 990 candidats ne peut pas exclure une occurrence rare (à ~1 % de taux réel,
  ~30 occurrences attendues sur le total, la probabilité de 0 sur 50 tirages reste
  significative mais pas nulle) : signal rassurant, non une preuve d'absence totale.
- `shell_prompt_host` : 11 signalements sur 4 lignes, tous relus individuellement (pas un
  échantillon, l'ensemble complet) : **0 hôte réel**. Le motif capture systématiquement
  la notation d'interface virtuelle macOS `if2` (`ifconfig`, format `en0@if2:`) et un cas
  de ratio numérique suivant un `@`, pas un identifiant de session shell.
- Toutes les autres règles (clé/jeton de fournisseur, e-mail obfusqué, numéro de série,
  IMEI, chemin home élargi, champ `hostnamectl`) : **0 signalement** sur les 2 593
  lignes.

Presidio (moteur NER dédié PII, évoqué comme option par la tâche) n'a pas été installé :
`RTX 3060` est l'hôte Proxmox de production (invariant « aucune VM touchée »), `pip`
n'est même pas présent sur le `python3` système, et la partition racine n'a que 8,8 Go
libres sur 94 Go (91 % pleine) — un environnement virtuel spaCy + Presidio + modèle pèse
couramment 0,5 à 1,5 Go, un risque jugé disproportionné par rapport au gain sur un jeu
déjà composé de sorties de terminal structurées (peu de prose naturelle, terrain où
Presidio apporte le plus). Repli explicitement prévu par la tâche : règles
supplémentaires indépendantes, appliquées ci-dessus.

### Contamination

Aucune ligne du jeu ne contient le canari du banc
(`termspeak-canary-v1-5e0c83a1d7f2`) : vérifié par `build_dataset_release.py` avant
écriture (le script refuse d'écrire s'il en trouve une), 0 trouvaille sur cette
exécution. Contrôle inverse de celui du banc
(`benchmark/tools/check_contamination.py`, qui vérifie qu'aucun cas du banc ne fuit dans
l'entraînement).

### Limites et biais

- Entraîné et évalué en français pour toutes les tâches ; l'anglais ne couvre que le
  résumé principal (`summary`), pas encore `detail`/`start`/`progress`/`flux`/`qa`.
- Couvre des sorties d'outils Linux et macOS courants (compilateurs, git, gestionnaires
  de paquets, réseau, disques, matériel, conteneurs) ; pas de Windows.
- `detail` porte un taux d'invention résiduel mesuré par le juge à 26 % avant filtrage
  (le journal de mission interne (non publié)) ; le jeu ci-dessus est déjà filtré à ce niveau, pas à zéro.
- Les lignes `sft`/`summary` sans capture brute disponible (`snapshot-*`, `resynced:
  false`) n'ont pas été revérifiées contre le code actuel de `steph.digest` : elles
  peuvent avoir dérivé légèrement du format de production si celui-ci a changé depuis
  leur étiquetage.
- `dpo` est vide dans ce brouillon : les triplets de préférence dépendent d'un modèle SFT
  déjà entraîné pour générer les réponses rejetées, donc du round d'entraînement final
  lui-même, pas de cette étape d'assemblage.
- Le déséquilibre par tâche (`summary` et `detail` dominent, `flux` et
  `summary_residual` sont marginaux) reflète la fréquence réelle des fonctionnalités dans
  steph, pas un choix d'échantillonnage.

### Maintenance

- Maintenu par l'auteur via les issues du dépôt `steph`.
- Reconstruit par `bench/matrix/finetune/build_dataset_release.py` (reproductible,
  testé — `tests/test_build_dataset_release.py`) à partir du corpus finalisé sur
  RTX 3060 ; jamais édité à la main.
- **Version publiée = celle du réentraînement final** (le journal de mission interne (non publié)) : ce
  brouillon documente une exécution de validation antérieure à ce réentraînement, pas le
  jeu final. Toute valeur chiffrée ci-dessus est à recalculer après le réentraînement
  final avant publication.

### Citation

Voir [`CITATION.cff`](../bench/matrix/finetune/CITATION.cff) (brouillon, à compléter avec
le nom de dépôt final une fois le réentraînement terminé et le dépôt publié).

### Contact

Signalement de faille ou de donnée personnelle résiduelle : voir `SECURITY.md` du dépôt.

## Non vérifié dans ce brouillon

| Point | Raison |
|---|---|
| Tailles et répartitions ci-dessus | mesurées avant le réentraînement final ; le corpus final peut différer (nouveau prompt, nouveau corpus, composition multilingue encore en cours) |
| `dpo` : contenu réel | dépend d'un modèle SFT entraîné, pas encore disponible |
| Absence totale de PII | deux audits automatisés à 0 trouvaille confirmée sur échantillon, pas une garantie exhaustive (voir la note statistique dans la section Anonymisation) |
| Lignes `resynced: false` | non revérifiées contre le code actuel de `steph.digest`/`steph.prompts`, faute de capture brute disponible pour les recalculer |
