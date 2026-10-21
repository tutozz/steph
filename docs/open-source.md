# Audit open source : Steph Speak Bench, modèle affiné, jeu d'entraînement

Tâche O1 du journal de mission interne (non publié) (analyse et recommandations, section 5 ci-dessous).
Tâche O2 (section « Décisions prises », juste après) : mise en conformité du dépôt selon
les décisions prises par l'utilisateur le 2026-09-27. Aucune publication, aucun dépôt
distant créé dans O1 ni O2 : tout reste privé tant que l'utilisateur ne l'ordonne pas (O3).

Le benchmark s'appelait TermSpeak au moment de l'audit O1 (sections 1 à 5 ci-dessous) ; il
est cité sous ce nom dans le corps de l'audit pour ne pas réécrire l'historique. Son nom
public est devenu **Steph Speak Bench** en O2 (voir Décisions prises, D-nommage) et a été
appliqué à toutes les chaînes publiques du dossier `benchmark/` (README, `CITATION.cff`,
`croissant.json`, `data/README.md`, `run.py`, `tools/`). Les documents de suivi interne
(le journal de mission interne (non publié), `docs/efficiency.md`, `docs/models-table.md`,
`docs/research-dataset-release.md`) et les fichiers `benchmark/results/*.json` déjà écrits
gardent le nom `termspeak` : ce sont des enregistrements historiques, pas des artefacts
publics, et les réécrire romprait la traçabilité (des résultats horodatés, un journal
d'optimisation) sans bénéfice. Le canari anti-contamination
(`termspeak-canary-v1-5e0c83a1d7f2`, `data/v1/schema.json`) garde aussi son nom d'origine :
`data/v1` est figé une fois publié (`benchmark/data/README.md`, section Maintenance), et le
renommer aurait changé le contenu des quatre fichiers `.jsonl` et désynchronisé les sommes
de contrôle déjà enregistrées dans `benchmark/results/*.json`. Un canari `steph-speak-bench-
canary-v2-...` est le bon endroit pour ce renommage, avec `data/v2`.

## Décisions prises (O2, 2026-09-27)

L'utilisateur a tranché les 9 questions de la section 5 (Décisions à soumettre). Table de
correspondance avec les options d'origine :

| # | Décision | Écart avec la recommandation O1 |
|---|---|---|
| D1 | Modèle affiné (base Granite ou Qwen) : **Apache 2.0** | aucun, recommandation suivie |
| D2 | Scripts d'entraînement `bench/matrix/finetune/` : **MIT** | aucun |
| D3 | Jeu d'entraînement : **CC BY 4.0** (remplace le choix CC BY-NC 4.0 de I1) | aucun, recommandation suivie ; corrige I1 |
| D4 | Base publiée : **Granite ou Qwen seulement**, Gemma 3 exclu | aucun |
| D5 | Espace de noms public : **organisation `lsmdx`** | aucun, mais collision trouvée sur GitHub (voir Collisions ci-dessous) |
| D6 | Dépôt du banc : pas tranché explicitement dans ce lot ; le nommage (D-nommage) prépare un dépôt dédié `steph-speak-bench`, la décision de l'extraire du monorepo reste ouverte pour O3 | ouvert |
| D7 | Contributions au code steph : **CLA** (texte type Apache ICLA / Harmony CLA, `CLA.md`, sans bot) | aucun |
| D8 | Split test : **public avec canari**, valeur du canari conservée (voir ci-dessus) | aucun |
| D9 | Schéma de nommage (section 2.2) : **adopté** | aucun |
| D-nommage | Marque partout : **Steph Speak Bench** (benchmark), plus de « TermSpeak » dans les chaînes publiques ; modèle `steph-speak[-<langue>]-<base>-<taille>-<méthode>-v<maj>.<min>-<quant>` ; jeu `lsmdx/steph-speak-train` | remplace le nom `TermSpeak` que O1 avait jugé « utilisable » (section 2.5) |

### Ce que O2 a fait

| Écart de la section 4 | Fait en O2 | Preuve |
|---|---|---|
| 1. Scripts d'entraînement sous PolyForm NC | `LICENSE` MIT ajouté à `bench/matrix/finetune/`, en-tête SPDX sur ses 34 fichiers `.py` (récursif, `efficiency/`, `pref/`, `vocab/`) | `bench/matrix/finetune/LICENSE`, commit `chore(finetune): licence MIT et en-têtes SPDX...` |
| 2. Aucune licence déclarée pour le modèle | Brouillon de carte avec `license: apache-2.0` | `docs/model-card-draft.md` |
| 5. Pas de CLA | `CLA.md` à la racine, référencé dans `CONTRIBUTING.md` | `CLA.md`, `CONTRIBUTING.md` |
| 6. Environnement d'entraînement non figé | Fichier dédié, mais versions non capturées (voir Non vérifié) | `bench/matrix/finetune/TRAINING_ENV.md` |
| 7. Noms de GGUF ad hoc | Schéma D9 documenté dans le brouillon de carte, pas encore appliqué à un fichier réel (aucun GGUF n'est renommé par O2 : ils vivent hors dépôt) | `docs/model-card-draft.md` |
| 8. Fichiers de communauté absents | `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CLA.md`, `CHANGELOG.md`, `.github/ISSUE_TEMPLATE/*`, `.github/PULL_REQUEST_TEMPLATE.md`, `benchmark/CONTRIBUTING.md` (`GOVERNANCE.md` couvert par une section de `CONTRIBUTING.md` plutôt qu'un fichier séparé) | fichiers listés |
| 9. Banc dans un dépôt à licence racine PolyForm | Pas résolu par O2 (nécessite d'extraire `benchmark/` en dépôt séparé, décision D6 encore ouverte) ; renommage TermSpeak -> Steph Speak Bench fait en attendant | section « Reste à faire » |
| 12. Licence LFM2.5 non lue | Non fait en O2 (pas dans le périmètre de la tâche transmise ; nécessite de lire le texte de la licence `lfm1.0`) | voir Non vérifié |
| 15. En-têtes SPDX limités au banc | Étendus à `bench/matrix/finetune/` (34 fichiers) ; conformité REUSE complète (dossier `LICENSES/`) non faite | commit SPDX ci-dessus |

Item 3 (relecture humaine des 210 cas), 4 (carte du jeu d'entraînement, carte de modèle
finale), 10 (étiquette git, DOI), 11 (prompt système livré avec le GGUF), 13 (`NOTICE`),
14, 16, 17 restent hors du périmètre transmis à O2 (assignés à A10, I2, R1 ou après O3 dans
la section 4).

### Collisions de noms, revérifiées le 2026-09-27

En plus de la vérification O1 (section 2.5, sur `TermSpeak` et `steph-speak`) :

| Nom | Hugging Face | PyPI | GitHub | npm | Verdict |
|---|---|---|---|---|---|
| `steph-speak-bench` | aucun modèle ni jeu (`api/models`, `api/datasets`, recherche vide) | libre (`pypi.org/pypi/.../json` → 404) | aucun dépôt (`search/repositories` → 0 résultat) | libre (`registry.npmjs.org` → 404) | libre |
| `steph-speak` | aucun (reconfirmé) | libre (reconfirmé) | aucun dépôt exact (3 résultats flous sur "steph"+"speak", aucun nommé `steph-speak`) | libre (reconfirmé) | libre |

**Collision trouvée, à traiter avant O3** : le nom d'utilisateur GitHub `lsmdx` existe déjà
(`api.github.com/users/lsmdx`, id `97398245`, créé le 2022-01-09, profil vide, 0 dépôt
public). Sur GitHub, noms d'utilisateur et noms d'organisation partagent le même espace de
noms : tant que ce compte existe, **l'organisation `lsmdx` ne peut pas être créée sur
GitHub** sous ce nom exact. Deux issues possibles, à trancher par l'utilisateur (il est seul
à savoir s'il possède déjà ce compte, ouvert il y a plusieurs années, cohérent avec le
domaine `lsmdx.com`) : (a) c'est un compte personnel déjà possédé par l'utilisateur, à
transformer en organisation ou à utiliser tel quel ; (b) c'est un tiers, et il faut soit le
contacter, soit choisir une variante (`lsmdx-ai`, `get-lsmdx`, etc.) pour le seul espace de
noms GitHub, en gardant `lsmdx` sur Hugging Face où il est confirmé libre. Rien sur PyPI et
npm n'est bloquant : l'espace de noms `lsmdx` n'y est utilisé que si un paquet est publié un
jour, non prévu à ce stade.

Périmètre : cinq artefacts.

| Artefact | Emplacement actuel | Licence actuelle |
|---|---|---|
| Terminal parlant steph (`src/`, `scripts/`, `site/`) | dépôt privé `tutozz/steph` | PolyForm Noncommercial 1.0.0 + licence commerciale (`COMMERCIAL.md`) |
| Code du benchmark TermSpeak (`benchmark/run.py`, `benchmark/tools/`) | même dépôt | MIT (`benchmark/LICENSE-CODE`) |
| Données du benchmark (`benchmark/data/`, `benchmark/results/`) | même dépôt | CC BY 4.0 (`benchmark/LICENSE-DATA`) |
| Scripts d'entraînement et de préparation (`bench/matrix/finetune/`) | même dépôt | PolyForm NC par défaut (aucune licence propre au dossier) |
| Modèle affiné (GGUF) | machines du labo, hors git (`bench/matrix/finetune/models/`) | aucune déclarée |
| Jeu d'entraînement (3 538 étiquettes, 2 165 retenues) | machines du labo, hors git | CC BY-NC 4.0 décidé en I1, pas encore appliqué |

## Résumé

| Axe | Constat |
|---|---|
| Bases candidates | **Granite 4.0 H 350M et Qwen3.5 0.8B : Apache 2.0**, aucune contrainte sur la licence du modèle affiné. **Gemma 3 270M : Gemma Terms of Use**, contrainte héritée par tout dérivé, pas open source |
| Étiquettes du corpus | produites par Qwen3.5 9B, **Apache 2.0** : aucune clause sur l'usage des sorties pour entraîner |
| PolyForm NC, CC BY-NC | **ni OSI, ni « open source »** : une clause non commerciale viole le critère 6 de l'Open Source Definition |
| Point bloquant caché | les **scripts d'entraînement** sont sous PolyForm NC : cela empêche le modèle d'être « Open Source AI » (OSAID exige le code d'entraînement sous licence OSI), quelle que soit la licence des poids |
| Benchmark | déjà au niveau des standards (carte, Croissant, CFF, canari, contamination) ; manquent la relecture humaine des 210 cas, un dépôt public autonome, un DOI, l'intégration aux outils d'évaluation |
| Nommage | GGUF actuels ad hoc (`soup-granite-uniform-Q4_K_M.gguf`) ; schéma proposé calé sur la convention GGUF de llama.cpp |
| Collisions | `TermSpeak` : mod de jeu vidéo et outil TTS `term-speak` homonymes, rien sur Hugging Face ni PyPI ; `steph` : compte HF `Steph` pris, PyPI libre |

## 1. Licences

### 1.1 Bases candidates

Licences lues via l'API Hugging Face le 2026-09-27 (champ `license` de la carte).

| Base | Licence | Accès | Obligations pour un dérivé | Liberté de licence du dérivé |
|---|---|---|---|---|
| `ibm-granite/granite-4.0-h-350m` | `apache-2.0` | libre | joindre la licence Apache, garder le NOTICE éventuel, signaler les fichiers modifiés | totale : Apache 2.0 (section 4) autorise des conditions différentes pour ses propres modifications |
| `Qwen/Qwen3.5-0.8B` | `apache-2.0` | libre | idem | totale |
| `google/gemma-3-270m(-it)` | `gemma` (Gemma Terms of Use, modifiées le 2026-04-01) | accès contrôlé (`gated: manual`) | reporter les restrictions d'usage (section 3.2 et Prohibited Use Policy) dans toute licence du dérivé ; joindre le texte complet ; fichier Notice « Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms » ; signaler les modifications | partielle : on peut ajouter des conditions (section 3.1), jamais retirer celles de Google ; Google se réserve un droit de restriction à distance |
| `Qwen/Qwen3.5-9B` (enseignant, juge) | `apache-2.0` | libre | aucune sur les sorties | sans objet |
| `google/gemma-4-E2B-it` (référence du classement) | `apache-2.0` | libre | sans objet | sans objet |
| `LiquidAI/LFM2.5-1.2B-Instruct` (référence du classement) | `other`, `lfm1.0` | libre | sans objet ici, sauf sorties dans `benchmark/results/` (voir 1.5) | sans objet |

Point Gemma à retenir : la définition de « Model Derivatives » couvre aussi un modèle
entraîné sur des sorties de Gemma (distillation, données synthétiques). Vérifié dans le code :
les paires DPO de P16 viennent des sorties de Granite (`bench/matrix/finetune/pref/run_pref.sh:5-6`)
et les étiquettes de Qwen3.5 9B. Aucun modèle Granite ou Qwen de steph n'hérite donc des
conditions Gemma. Seule la variante `steph-gemma3-270m` les porte.

**Conséquence** : publier la variante Gemma 3 impose `license: gemma` sur Hugging Face et
exclut toute licence OSI pour ce fichier. Gemma 4 est passé en Apache 2.0 ; ce n'est pas le
cas de Gemma 3.

### 1.2 Non commercial contre open source

| Référentiel | Ce qu'il exige | PolyForm NC | CC BY-NC 4.0 |
|---|---|---|---|
| Open Source Definition, critère 6 | aucune restriction de domaine d'usage, « it may not restrict the program from being used in a business » | non conforme | non conforme (et CC déconseille ses licences pour du logiciel) |
| Open Source AI Definition 1.0 | poids sous « OSI-approved terms » ; code d'entraînement et de traitement des données sous licence OSI ; « Data Information » sous conditions OSI. **Le jeu brut lui-même n'est pas exigé** | non conforme si appliqué aux poids ou au code | non conforme si appliqué aux poids ; **compatible si appliqué au seul jeu de données**, à condition que la carte et les scripts soient ouverts |
| Model Openness Framework (LF AI & Data) | classe III : poids et cartes ; classe I : jeu de données inclus sous licence de données ouverte | exclut les classes | le jeu NC ne compte pas pour la classe I (lecture du cadre, à confirmer avec l'outil isitopen.ai) |
| OpenRAIL-M | restrictions d'usage éthiques, commercial permis | sans objet | sans objet ; les licences RAIL se déclarent elles-mêmes « NOT OPEN SOURCE » au sens OSI |

Effets pratiques d'une licence non commerciale, sur les artefacts publiés :

| Effet | Détail |
|---|---|
| Vocabulaire | interdit de dire « open source » ; dire « poids ouverts, usage non commercial » ou « source disponible » (déjà la règle du site steph) |
| Hugging Face | aucun blocage : `cc-by-nc-4.0` est un identifiant natif ; PolyForm n'existe pas dans la liste, il faudrait `license: other` + `license_name` + fichier LICENSE |
| Filtres d'entreprise | les équipes juridiques filtrent souvent sur Apache/MIT ; un modèle NC sort des sélections automatiques (licence affichée et filtrable sur le Hub) |
| Réutilisation par d'autres projets | un projet Apache ou MIT ne peut pas embarquer un artefact NC sans devenir NC lui-même en pratique ; frein direct à « facile à reprendre » |
| Contributions | un contributeur hésite à donner du travail gratuit à un artefact qu'un tiers vend sous licence commerciale ; et le **double licenciement exige une CLA** (voir 1.4) |
| Ambiguïté juridique | « non commercial » est flou (usage interne d'une entreprise, association qui facture) ; source de questions sans fin dans les issues |

### 1.3 Options par artefact

| Artefact | Option | Avantages | Risques |
|---|---|---|---|
| Code steph (`src/`) | **PolyForm NC + commercial (actuel)** | protège le produit vendu | pas open source ; contributions freinées ; CLA obligatoire |
| | Apache 2.0 | adoption, contributions | perte du levier commercial sur le logiciel |
| | AGPL-3.0 + commercial | OSI, protège contre le SaaS fermé | ne protège pas contre un usage commercial interne ; CLA quand même |
| Code du benchmark | **MIT (actuel)** | standard des benchmarks, zéro friction | aucun |
| Données du benchmark | **CC BY 4.0 (actuel)** | standard des benchmarks (MMLU, GPQA, etc.), citable | aucun sérieux |
| | CC BY-NC 4.0 | cohérent avec steph | les laboratoires et harnais d'évaluation éviteraient le banc ; contre-productif pour un benchmark |
| Scripts d'entraînement (`bench/matrix/finetune/`) | **MIT ou Apache 2.0** | débloque OSAID, reproductibilité par des tiers | un concurrent réutilise la recette (faible valeur isolée : la valeur est dans le corpus et le digest de steph) |
| | PolyForm NC (actuel) | cohérent avec steph | bloque OSAID quel que soit le reste |
| Modèle affiné (base Apache) | **Apache 2.0** | même licence que la base, filtre « apache-2.0 » du Hub, OSI, compatible Ollama, LM Studio, distributions | un concurrent réutilise le modèle ; limité car il faut aussi le digest, le prompt et l'intégration shell de steph (PolyForm) |
| | OpenMDW-1.1 | licence permissive pensée pour poids + données + code, adoptée par NVIDIA ; identifiant HF natif `openmdw-1.1` | soumise à l'OSI en août 2026, pas encore approuvée ; moins connue qu'Apache |
| | CC BY-NC 4.0 | protège le levier commercial | pas open source ; licence CC déconseillée pour du logiciel, ambiguë pour des poids |
| | PolyForm NC | cohérent avec le code | `license: other`, inconnue de la communauté ML |
| | OpenRAIL-M | cadre éthique | friction, pas OSI, n'empêche pas l'usage commercial |
| Modèle affiné (base Gemma 3) | `gemma` imposé, éventuellement + NC | seule option légale | pas open source, accès et restrictions Google |
| Jeu d'entraînement | **CC BY-NC 4.0 (décidé en I1)** | protège l'effort d'étiquetage | classe I du MOF inaccessible ; ne protège rien si le modèle est Apache (on réutilise le modèle, pas le jeu) |
| | CC BY 4.0 | cohérence totale « ouvert », crédit scientifique maximal, même licence que le banc | un concurrent entraîne son propre modèle commercial dessus |
| | CDLA-Permissive-2.0 | licence de données écrite pour le ML, n'impose rien sur le modèle entraîné | moins connue que CC BY |

### 1.4 Contributions et double licence

`COMMERCIAL.md` vend le code steph sous une autre licence. Un correctif externe reçu sous
PolyForm NC ne peut **pas** être revendu sous licence commerciale sans l'accord de son
auteur. Deux solutions standard :

| Solution | Effet |
|---|---|
| CLA (Contributor License Agreement), par exemple CLA Assistant sur GitHub | le contributeur accorde une licence large ; nécessaire pour le code steph tant qu'il est vendu |
| DCO (`Signed-off-by`) | certifie l'origine, **ne suffit pas** à relicencier commercialement ; suffisant pour les artefacts Apache, MIT, CC BY |

Pour le benchmark et un modèle Apache, pas de CLA : « inbound = outbound » (la contribution
arrive sous la licence du projet) suffit, avec DCO.

### 1.5 Données du corpus et des résultats

| Sujet | Constat | Action |
|---|---|---|
| Sorties de commandes capturées | faits bruts pour l'essentiel (chiffres, chemins, messages) ; quelques textes d'outils peuvent être protégés (descriptions de paquets, bannières de licence) | relever dans la datasheet ; retirer les longs textes descriptifs si l'audit PII les voit |
| Données personnelles | anonymisation scriptée (`audit_pii.py`, `clean_pii.py`), scanner à 0 ; audit indépendant prévu en I2 | publier une procédure de retrait et un contact dans la carte du jeu |
| Étiquettes Qwen3.5 9B | Apache 2.0, aucune clause sur les sorties (contrairement à certains Qwen antérieurs et à Gemma) | citer le modèle enseignant et sa licence dans la carte |
| Sorties de modèles dans `benchmark/results/` (CC BY 4.0) | Gemma : « Google claims no rights in Outputs » ; Apache : sans objet ; LFM2.5 (`lfm1.0`) : **clause sur les sorties non lue** | lire la licence LFM avant publication, ou retirer les textes générés des résultats LFM |
| Liste de mots `src/steph/data/english_words.txt.gz` | CC BY-SA 4.0 (wordfreq, Lexique), déclarée dans `NOTICE` | sans effet sur le modèle ni le banc ; à garder hors des dépôts du modèle |

### 1.6 Recommandation

**Combinaison recommandée : « modèle ouvert, produit protégé ».**

| Artefact | Licence recommandée | Changement |
|---|---|---|
| Code steph | PolyForm NC + commercial | aucun ; ajouter une CLA |
| Code du benchmark | MIT | aucun |
| Données du benchmark | CC BY 4.0 | aucun |
| Scripts d'entraînement et de préparation | MIT (même licence que le code du banc) | oui : `LICENSE` dans `bench/matrix/finetune/` |
| Modèle affiné sur Granite ou Qwen | Apache 2.0 | oui : première licence déclarée |
| Modèle affiné sur Gemma 3 | ne pas publier en public ; sinon `gemma` | décision |
| Jeu d'entraînement | CC BY 4.0 (recommandé) ou CC BY-NC 4.0 (choix I1 maintenu) | décision |

Arguments :

- Le modèle seul ne reproduit pas steph : il faut le digest, le prompt, `resolve()`, le garde-fou d'ancrage et l'intégration shell, tous sous PolyForm. Le levier commercial reste entier.
- Apache 2.0 est la licence des deux bases retenues : aucune couche juridique ajoutée, filtre du Hub, OSAID atteignable.
- Un jeu CC BY-NC avec un modèle Apache protège peu : un concurrent prend le modèle, pas le jeu. Le seul effet réel est de fermer la classe I du MOF et le crédit « recherche ouverte ».
- Les scripts d'entraînement sous MIT sont la condition la moins chère pour que le modèle compte comme Open Source AI.

## 2. Nommage versionné

### 2.1 Conventions observées

| Famille | Dépôt | Fichier GGUF |
|---|---|---|
| llama.cpp (spécification GGUF) | sans objet | `<BaseName>-<SizeLabel>-<FineTune>-<Version>-<Encoding>-<Type>-<Shard>.gguf`, version `v<Maj>.<Min>`, ex. `Mixtral-8x7B-v0.1-KQ2.gguf` |
| IBM Granite | `ibm-granite/granite-4.0-h-350m`, `...-GGUF` | `granite-4.0-h-350m-Q4_K_M.gguf` |
| Qwen (via unsloth) | `Qwen/Qwen3.5-0.8B`, `unsloth/Qwen3.5-0.8B-GGUF` | `Qwen3.5-0.8B-Q4_K_M.gguf` |
| bartowski | `bartowski/<org>_<modèle>-GGUF`, ex. `bartowski/google_gemma-3-270m-it-GGUF` | `<org>_<modèle>-<quant>.gguf` |
| SmolLM2 | `HuggingFaceTB/SmolLM2-360M-Instruct-GGUF` | `smollm2-360m-instruct-q8_0.gguf` |
| Llama | `meta-llama/Llama-3.2-1B-Instruct` | version dans le nom de famille, taille, variante |

Constantes : la version de famille entre dans le nom, la taille en suffixe `350M`, la
quantification en dernier segment majuscule (`Q4_K_M`), un dépôt `-GGUF` séparé du dépôt de
poids, le dépôt de base déclaré dans `base_model`.

### 2.2 Schéma proposé pour le modèle

```
<famille>-<tâche>[-<langue>]-<base>-<taille>-<méthode>-v<maj>.<min>-<quant>.gguf
```

| Segment | Valeurs | Règle |
|---|---|---|
| famille | `steph` | fixe |
| tâche | `speak` (résumé vocal de sortie de terminal) ; plus tard `qa`, `detail` si des modèles séparés apparaissent | un mot, anglais |
| langue | absent = cible fr + en ; `fr` ou `en` si le modèle n'est entraîné et évalué que sur une langue | les modèles actuels sont entraînés en français seulement : `-fr` tant que H3 n'a pas ajouté l'anglais |
| base | `granite-4.0-h`, `qwen3.5`, `gemma-3` | nom de la base en minuscules, tel que l'éditeur l'écrit |
| taille | `350M`, `0.8B`, `270M` | convention GGUF |
| méthode | `sft`, `dpo` | la soupe et la graine vont dans la carte, pas dans le nom |
| version | `v1.0` | **majeure** = format d'entrée ou prompt changé (incompatible avec une version de steph) ; **mineure** = réentraînement au même format |
| quant | `Q4_K_M`, `Q8_0`, `F16` | convention llama.cpp |

Exemples :

```
steph-speak-fr-granite-4.0-h-350M-dpo-v1.0-Q4_K_M.gguf
steph-speak-fr-qwen3.5-0.8B-sft-v1.0-Q8_0.gguf
```

Dépôts Hugging Face :

| Dépôt | Contenu |
|---|---|
| `<org>/steph-speak-fr-granite-4.0-h-350M-v1` | poids fusionnés safetensors, carte, `LICENSE`, `NOTICE` |
| `<org>/steph-speak-fr-granite-4.0-h-350M-v1-GGUF` | GGUF Q4_K_M, Q8_0, F16 ; fichiers `system` et `params` pour Ollama |
| `<org>/steph-speak-fr-granite-4.0-h-350M-v1-LoRA` | adaptateur seul (optionnel) |
| Collection `steph speak v1` | regroupe les bases et quantifications d'une même version |

Une version mineure s'étiquette en révision git du dépôt HF (`v1.1`), la majeure ouvre un
nouveau dépôt (`-v2`) et renseigne `new_version` dans l'ancien. La carte déclare la version
minimale de steph compatible (lien avec P18).

### 2.3 Schéma proposé pour le benchmark

| Élément | Proposition |
|---|---|
| Nom | `TermSpeak` (inchangé) |
| Version | semver du jeu : **1.0.0** actuelle (déjà dans `CITATION.cff` et `croissant.json`) |
| Majeure | cas modifiés ou retirés, notation changée : scores non comparables, dossier `data/v2/` (règle déjà écrite dans le README) |
| Mineure | ajout de langue, de catégorie ou de split sans toucher l'existant : `1.1.0` |
| Correctif | métadonnées ou documentation sans effet sur les scores : `1.0.1` |
| Configurations HF | `en`, `fr` (déjà), plus tard `de`, `es` |
| Splits | `dev`, `test` (déjà) ; réserver `test-hidden` pour un éventuel split privé |
| Dépôts | `<org>/termspeak` (Datasets, avec `eval.yaml`) ; dépôt GitHub `<org>/termspeak` |
| Étiquettes git | `termspeak-v1.0.0` |
| Classement | chaque résultat porte la version du jeu (le fichier stocke déjà les sommes de contrôle) |

### 2.4 Schéma proposé pour le jeu d'entraînement

| Élément | Proposition |
|---|---|
| Dépôt | `<org>/steph-speak-train` |
| Configurations | `sft` (paires `messages`), `dpo` (paires préférées/rejetées) |
| Splits | `train`, `validation` (déjà déterministes par SHA-256) |
| Version | `v1.0` alignée sur la version majeure du modèle qu'il entraîne |

### 2.5 Collisions de noms

Vérifié le 2026-09-27 (API Hugging Face, PyPI, `gh search repos`, npm, recherche web).

| Nom | Hugging Face | PyPI | GitHub | Autres | Verdict |
|---|---|---|---|---|---|
| `TermSpeak` | aucun modèle, jeu, compte | libre | `KodiCraft/TermSpeak` (mod Lethal Company, 0 étoile), `abi/termspeak` (2), `Tridhatri/TermSpeak` (0) ; `Cspeisman/term-speak` (TTS pour iTerm2, domaine voisin) | paquet npm `termspeak` (2011, inactif) ; mod sur Thunderstore | utilisable ; toujours écrire « TermSpeak benchmark » |
| `steph` | compte utilisateur `Steph` pris (vide) ; aucun modèle `steph-*` | libre | `ronyhe/steph` (13 étoiles), nombreux dépôts personnels | nom commun, faible trouvabilité | utiliser un espace de noms d'organisation, jamais `steph/` seul |
| Espace de noms | `tutozz` existe (propriétaire non vérifié) ; `lsmdx` libre | sans objet | `tutozz` (dépôt actuel) | domaine `lsmdx.com` | décision utilisateur |
| `steph-speak` | aucun | libre | aucun résultat pertinent | aucun | libre |

## 3. Standards de publication

### 3.1 Carte du modèle (Hugging Face)

En-tête YAML attendu :

| Champ | Valeur proposée |
|---|---|
| `license` | `apache-2.0` (ou `gemma` pour la variante Gemma) |
| `base_model` | `ibm-granite/granite-4.0-h-350m` |
| `base_model_relation` | `finetune` (poids fusionnés), `quantized` dans le dépôt GGUF, `adapter` pour le LoRA |
| `language` | `fr` (et `en` si évalué et assumé) |
| `datasets` | `<org>/steph-speak-train`, `<org>/termspeak` |
| `pipeline_tag` | `text-generation` |
| `library_name` | `gguf` (dépôt GGUF), `transformers` (poids) |
| `tags` | `accessibility`, `screen-reader`, `terminal`, `summarization`, `steph` |
| `new_version` | renseigné à la sortie de la version suivante |
| `co2_eq_emissions` | `emissions`, `source`, `training_type`, `geographical_location`, `hardware_used` |
| Résultats | fichier `.eval_results/termspeak.yaml` (nouveau format du Hub) ; `model-index` en repli |

Sections du corps (Mitchell et al., gabarit annoté HF) : description, usage prévu (résumé
vocal dans steph), **usages hors périmètre** (conseil sécurité, décision automatique,
contenu non terminal), limites et biais (entraîné en français, outils Linux et macOS,
pas de Windows, inventions mesurées au juge), prompt système exact et gabarit, recette
d'entraînement (r16 α32, lr, époques, 4 graines, soupe, DPO), matériel et durée,
évaluation (TermSpeak test, deux protocoles séparés comme dans `benchmark/README.md`),
contamination, empreinte carbone, licence et attributions, citation, contact.

### 3.2 Carte du jeu d'entraînement

| Élément | Standard | Source à réutiliser |
|---|---|---|
| En-tête YAML HF | `license: cc-by-nc-4.0` ou `cc-by-4.0`, `language`, `task_categories`, `size_categories`, `configs` | `benchmark/data/README.md` |
| Datasheet (Gebru et al.) | motivation, composition, **collecte sur machines réelles**, étiquetage par Qwen3.5 9B, filtrage au juge, anonymisation, retrait sur demande | `docs/research-dataset-release.md` |
| Croissant 1.0 + RAI | `croissant.json` généré | `benchmark/tools/make_croissant.py` |
| Contamination | sens inverse : aucune ligne du jeu ne contient le canari `termspeak-canary-v1-...` | `benchmark/tools/check_contamination.py` |

### 3.3 Citation, DOI, SPDX

| Standard | État | Proposition |
|---|---|---|
| `CITATION.cff` | banc seulement ; `repository-code` pointe vers le dépôt privé | un CFF par dépôt public ; URL publique ; champ `doi` |
| DOI | aucun | Zenodo (archivage des versions GitHub publiées) pour le code du banc ; bouton « Generate DOI » du Hub (DataCite) pour le jeu et le modèle. Attention : un DOI HF **verrouille** suppression, renommage et changement de visibilité |
| SPDX | 13 fichiers d'en-tête, tous dans `benchmark/` | en-tête `SPDX-License-Identifier` sur tout fichier publié ; conformité REUSE (dossier `LICENSES/`) pour un dépôt à plusieurs licences |
| GGUF | métadonnées `general.*` non contrôlées | vérifier `general.name`, `general.license`, `general.base_model.*` et `tokenizer.chat_template` dans chaque GGUF |

### 3.4 Fichiers de communauté

| Fichier | Rôle | Remarque pour steph |
|---|---|---|
| `README.md` | entrée | existe (steph, banc) |
| `CONTRIBUTING.md` | comment contribuer, tests, style | indiquer CLA (code steph) ou DCO (banc, modèle) |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1 | standard GitHub |
| `SECURITY.md` | signalement privé des failles | pertinent : steph lit toutes les sorties du shell |
| `GOVERNANCE.md` | qui décide, comment un cas entre dans le banc | un mainteneur (BDFL) au départ, le dire |
| `.github/ISSUE_TEMPLATE/` | bug, nouveau cas TermSpeak, soumission de résultat | formulaire « résultat » : modèle, backend, matériel, fichiers |
| `.github/PULL_REQUEST_TEMPLATE.md` | liste de contrôle | validation `tools/validate.py`, scanner PII à 0 |
| `CHANGELOG.md` | format Keep a Changelog, semver | un par artefact publié |
| `NOTICE` | attributions | modèle : base Granite ou Qwen, enseignant Qwen3.5 9B ; Gemma : texte de Notice imposé |

### 3.5 Classement et soumission

| Question | État | Recommandation |
|---|---|---|
| Procédure de soumission | PR avec fichiers `results/*.json`, protocole inchangé (`benchmark/README.md`, section Submit a result) | garder ; ajouter un gabarit d'issue « résultat » et une CI qui refuse un résultat sans sommes de contrôle valides |
| Split test caché | test public, canari, 0 cas contaminé | garder public (reproductibilité, adoption) ; prévoir un `test-hidden` privé à la version 2 si des scores suspects apparaissent |
| Matériel | tous les résultats sur Apple M3 Pro | colonne matériel déjà présente ; ne jamais trier la latence entre matériels différents |
| Classement sur le Hub | aucun | `eval.yaml` dans le dépôt Datasets (enregistrement « Benchmark » en bêta, liste d'autorisation) ; résultats des modèles via `.eval_results/` |

### 3.6 Reproductibilité

| Élément | État | Écart |
|---|---|---|
| Graines | `--seed 42` par défaut, graines 42, 7, 123, 2024 pour la soupe | documenté dans le suivi, pas dans une carte |
| Versions des bibliothèques d'entraînement | `uv.lock` couvre l'application, **pas** torch, transformers, peft du labo | environnement d'entraînement non figé |
| Prompt d'entraînement | `train_system_prompt.txt`, `train_system_prompt.en.txt` | à publier avec le modèle (fichier `system` pour Ollama) |
| Conversion GGUF | manuelle (recollage MTP pour Qwen3.5, rappel dans `train_lora.py`) | script de conversion et version de llama.cpp à consigner |
| Données | hors git, sur 4 machines | somme SHA-256 du jeu publiée dans la carte |

### 3.7 Intégration aux outils

| Outil | Ce qu'il faut | État |
|---|---|---|
| llama.cpp | GGUF avec `tokenizer.chat_template` ; `llama-server -hf <org>/<dépôt>:Q4_K_M` | runner du banc compatible OpenAI, déjà testé |
| Ollama | `ollama run hf.co/<org>/<dépôt>:Q4_K_M` sans Modelfile ; fichiers `system` (prompt steph), `params`, `template` si besoin, dans le dépôt GGUF | à faire ; le prompt système compte (C3 : écart de protocole mesuré) |
| LM Studio | GGUF sur le Hub, gabarit intégré | à faire, rien de spécifique |
| lm-evaluation-harness | tâche YAML `generate_until`, `dataset_path` HF, métrique regex via `!function utils.py` | absent ; nécessite le jeu sur le Hub |
| Inspect (UK AISI) | cadre d'évaluation du Hub pour les résultats vérifiés | option ultérieure |

## 4. État actuel contre les standards

Gravité : **haute** bloque une publication propre ; **moyenne** freine l'adoption ; **faible** confort.

| # | Écart | Gravité | Effort | Tâche |
|---|---|---|---|---|
| 1 | Scripts d'entraînement sous PolyForm NC : modèle jamais « Open Source AI » | haute | faible (décision + un `LICENSE`) | O2 |
| 2 | Aucune licence déclarée pour le modèle ; variante Gemma sous conditions Google | haute | faible | O2, A10 |
| 3 | Relecture humaine des 210 cas du banc non faite (C2) | haute | moyen (une journée) | nouvelle |
| 4 | Aucune carte de modèle ni carte de jeu d'entraînement | haute | moyen | A10, I2 |
| 5 | Pas de CLA alors que le code steph est vendu sous double licence | haute (juridique) | faible | O2 |
| 6 | Environnement d'entraînement non figé (torch, transformers, peft, llama.cpp) | moyenne | faible | O2 |
| 7 | Noms de GGUF ad hoc, sans version ni langue ni méthode | moyenne | faible | O2 |
| 8 | Fichiers de communauté absents (CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, GOVERNANCE, gabarits, CHANGELOG) | moyenne | faible | O2 |
| 9 | Banc dans un dépôt privé à licence racine PolyForm ; `CITATION.cff` et Croissant pointent vers une URL privée | moyenne | moyen (dépôt dédié) | O2, O3 |
| 10 | Aucune étiquette git ni version publiée, aucun DOI | moyenne | faible | O3 |
| 11 | Prompt système du modèle non livré avec le GGUF (Ollama, LM Studio l'ignorent) | moyenne | faible | A10 |
| 12 | Licence LFM2.5 non lue pour les sorties publiées dans `benchmark/results/` | moyenne | faible | O2 |
| 13 | NOTICE sans attribution des bases ni de l'enseignant | moyenne | faible | A10 |
| 14 | Pas d'intégration lm-evaluation-harness ni `eval.yaml` | faible | moyen | après O3 |
| 15 | En-têtes SPDX limités au banc, pas de conformité REUSE | faible | faible | O2 |
| 16 | Empreinte carbone non mesurée | faible | faible (heures GPU × puissance) | A10 |
| 17 | Métadonnées GGUF (`general.license`, `general.base_model`) non contrôlées | faible | faible | A10 |

Déjà conforme : carte de jeu du banc avec YAML HF, Datasheets, Croissant 1.0 + RAI,
JSON Schema, CFF 1.2, chaîne canari, contrôle de contamination publié, splits dev/test,
données versionnées et immuables, anonymisation vérifiée par scanner, deux protocoles
séparés au classement, CI sur Linux et macOS.

## 5. Décisions à soumettre

Recommandation en premier dans chaque ligne.

| # | Question | Options | Recommandation |
|---|---|---|---|
| D1 | Licence du modèle affiné (base Granite ou Qwen) | **Apache 2.0** ; OpenMDW-1.1 ; CC BY-NC 4.0 ; PolyForm NC | Apache 2.0 : même licence que la base, OSI, filtres du Hub ; le levier commercial reste dans le code steph |
| D2 | Licence des scripts d'entraînement `bench/matrix/finetune/` | **MIT** ; Apache 2.0 ; PolyForm NC (actuel) | MIT : condition OSAID, même licence que le code du banc |
| D3 | Licence du jeu d'entraînement | **CC BY 4.0** ; CC BY-NC 4.0 (choix I1) ; CDLA-Permissive-2.0 | CC BY 4.0 si D1 = Apache (le NC ne protège alors presque rien) ; sinon garder CC BY-NC |
| D4 | Base publiée | **Granite ou Qwen seulement** ; aussi Gemma 3 sous `gemma` | Granite ou Qwen : Gemma 3 ajoute des conditions Google et un accès contrôlé |
| D5 | Espace de noms public | **organisation `lsmdx`** (libre sur HF) ; compte `tutozz` ; nouvelle organisation `steph-ai` | `lsmdx` : cohérent avec le domaine, sépare l'identité personnelle |
| D6 | Dépôt du banc | **dépôt GitHub dédié `termspeak` + jeu HF** ; dossier du dépôt steph rendu public | dépôt dédié : licence racine claire (MIT + CC BY), issues propres au banc |
| D7 | Contributions au code steph | **CLA** ; DCO seul ; pas de contributions externes | CLA : seule façon de garder la licence commerciale sur le code contribué |
| D8 | Split test | **public avec canari** ; test caché dès v1 | public : reproductibilité et adoption ; caché plus tard si besoin |
| D9 | Schéma de nommage (section 2.2) | **adopter** ; ajuster les segments | adopter : calé sur la spécification GGUF et Granite/Qwen |

## Sources

- [Gemma Terms of Use, modifiées le 2026-04-01](https://ai.google.dev/gemma/terms)
- [Carte `ibm-granite/granite-4.0-h-350m`](https://huggingface.co/ibm-granite/granite-4.0-h-350m) et [dépôt GGUF officiel](https://huggingface.co/ibm-granite/granite-4.0-h-350m-GGUF)
- [Carte `Qwen/Qwen3.5-0.8B`](https://huggingface.co/Qwen/Qwen3.5-0.8B), [`Qwen/Qwen3.5-9B`](https://huggingface.co/Qwen/Qwen3.5-9B)
- [Carte `google/gemma-3-270m`](https://huggingface.co/google/gemma-3-270m), [`google/gemma-4-E2B-it`](https://huggingface.co/google/gemma-4-E2B-it)
- [Open Source Definition, critère 6](https://opensource.org/osd)
- [Open Source AI Definition 1.0](https://opensource.org/ai/open-source-ai-definition)
- [FAQ Creative Commons (logiciel, IA)](https://creativecommons.org/faq/)
- [FAQ OpenRAIL](https://www.licenses.ai/faq-2)
- [OpenMDW-1.1](https://openmdw.ai/license/1-1/), [annonce Linux Foundation](https://www.linuxfoundation.org/press/linux-foundation-releases-openmdw-1.1-nvidia-adopts-openmdw-for-cosmos-isaac-gr00t-ising-and-nemotron-ai-model-families), [soumission à l'OSI](https://www.opensourceforu.com/2026/08/linux-foundation-submits-openmdw-for-open-source-review/)
- [PolyForm NC n'est pas open source, Hacker News](https://news.ycombinator.com/item?id=31658939), [source-available software](https://en.wikipedia.org/wiki/Source-available_software)
- [Model Openness Framework, arXiv](https://arxiv.org/pdf/2403.13784)
- [Licences reconnues par Hugging Face](https://huggingface.co/docs/hub/repositories-licenses)
- [Cartes de modèle, Hugging Face](https://huggingface.co/docs/hub/model-cards)
- [Résultats d'évaluation et `eval.yaml`, Hugging Face](https://huggingface.co/docs/hub/eval-results)
- [DOI sur Hugging Face](https://huggingface.co/docs/hub/doi)
- [Intégration GitHub de Zenodo](https://help.zenodo.org/docs/github/)
- [Convention de nommage GGUF, ggml](https://github.com/ggml-org/ggml/blob/master/docs/gguf.md)
- [Ollama et GGUF du Hub](https://huggingface.co/docs/hub/ollama), [import GGUF dans Ollama](https://docs.ollama.com/import)
- [Ajouter une tâche à lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/new_task_guide.md)
- [Mod TermSpeak, Thunderstore](https://thunderstore.io/c/lethal-company/p/KodiCraft/TermSpeak/), [term-speak, GitHub](https://github.com/Cspeisman/term-speak)
- Recherche I1 : `docs/research-dataset-release.md` (Datasheets, Croissant, FMTI, CDLA)

## Reste à faire après O2

| Point | Assigné à |
|---|---|
| Réentraînement final, scores, latence, empreinte carbone (tous les champs « à remplir après R1 » de `docs/model-card-draft.md`) | R1 |
| Carte du jeu d'entraînement (`lsmdx/steph-speak-train`), carte de modèle finale, NOTICE avec attributions | A10, I2 |
| Versions figées de torch, transformers, peft, trl, mamba_ssm, causal_conv1d | capture manuelle sur chaque machine du labo, voir `bench/matrix/finetune/TRAINING_ENV.md` |
| Lecture de la licence `lfm1.0` pour les sorties LFM2.5 dans `benchmark/results/` | O2 suivant ou A10 |
| Relecture humaine des 210 cas du banc (C2), étiquette git et DOI, extraction de `benchmark/` en dépôt dédié (D6) | O3 |
| Résoudre la collision GitHub sur le nom d'utilisateur `lsmdx` (voir Collisions ci-dessus) | utilisateur, avant O3 |
| Publication effective (Hugging Face, GitHub public, PyPI) | O3, sur ordre explicite uniquement |

## Non vérifié

| Point | Raison |
|---|---|
| Texte intégral des licences Apache de Granite et Qwen3.5 0.8B | lu via le champ `license` de l'API, pas le fichier LICENSE complet |
| Clause sur les sorties de la licence `lfm1.0` | non lue |
| Seuils exacts de la classe I du MOF pour un jeu NC | déduit du cadre, pas testé sur isitopen.ai |
| Conditions de Zenodo (dépôt public requis, DOI de concept) | page d'aide sans le détail ; usage courant, non confirmé |
| Propriétaire du compte HF `tutozz` | non vérifié |
| Propriétaire du compte GitHub `lsmdx` (créé 2022-01-09, profil vide) | non vérifié ; seul l'utilisateur peut confirmer s'il le possède déjà |
| Versions réelles de torch, transformers, peft, trl, mamba_ssm, causal_conv1d sur les machines du labo | aucune trouvée dans le dépôt (ni le journal de mission interne (non publié), ni les scripts, ni `pyproject.toml`) ; `bench/matrix/finetune/TRAINING_ENV.md` documente la commande de capture mais ne les invente pas |
| Analyse juridique | aucune relecture par un juriste ; recommandations d'ingénieur |
