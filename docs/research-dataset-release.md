# Recherche : faut-il publier le jeu d'entraînement du LoRA steph

Tâche I1 du suivi de mission (le journal de mission interne (non publié)). Question posée : publier ou non
les 3 538 paires d'entraînement (sorties de commandes réelles anonymisées, 172 programmes
Linux et macOS, résumé télégraphique produit par Qwen3.5 9B) qui servent à affiner le petit
modèle universel de steph. Le jeu lui-même n'a pas été lu pour cette recherche ; l'analyse
s'appuie sur les scripts de composition et d'audit (`bench/matrix/finetune/`) et sur l'état
déjà publié du benchmark `benchmark/`.

## Résumé

| Axe | Constat |
|---|---|
| Adoption | Les modèles les plus adoptés (Llama, Mistral, Phi) ne publient pas leurs données d'entraînement ; l'adoption vient des poids ouverts et d'un banc public, pas du jeu d'entraînement |
| Confiance / reproductibilité | Publier la donnée ajoute un crédit scientifique réel mais auprès d'un public restreint (chercheurs, labels d'ouverture) ; aucun standard majeur ne l'exige pour être qualifié « open » |
| Standards | steph applique déjà, sur `benchmark/`, tout l'outillage qu'exigerait une publication du jeu d'entraînement (carte de jeu de données, Datasheets, Croissant, CITATION.cff, versionnage, contrôle de contamination) |
| Licence | Aucun obstacle légal (Qwen3.5 en Apache 2.0 pur) ; le choix de licence détermine surtout si des entreprises concurrentes peuvent réutiliser gratuitement ce que steph vend par ailleurs |
| Risque principal | PII résiduelle malgré l'audit automatisé, et infrastructure de test (noms d'hôtes, plans réseau) qui a déjà justifié un scanner dédié |
| Hébergement | Hugging Face Datasets est le choix par défaut du secteur pour ce type de corpus ; Zenodo ajoute un DOI pérenne à peu de frais |

## 1. Effet réel sur la visibilité, la confiance et l'adoption

### Ce que montrent les projets publiés

| Modèle / projet | Poids | Données d'entraînement | Effet observé |
|---|---|---|---|
| Llama, Mistral 7B, Phi | publics | non publiées | adoption massive ; « open-weight » suffit à la communauté de déploiement ([comparatif open-weight 2026](https://kingy.ai/blog/state-of-open-weight-ai-models/)) |
| Alpaca (Stanford) | publics | 52 000 exemples publiés, distillés de Text-Davinci-003 | premier modèle instruct open source largement repris, cité comme référence de reproductibilité ([Mini-Giants, arXiv](https://arxiv.org/pdf/2307.08189)) |
| Databricks Dolly 2.0 | publics | 15 000 exemples humains publiés (`databricks-dolly-15k`) | premier petit modèle instruct **à licence commerciale claire**, argument marketing explicite de Databricks |
| Vicuna | publics | 70 000 conversations ShareGPT, **jamais publiées telles quelles** (conditions d'utilisation de la source) | adoption forte malgré tout ; le jeu de données a été le point faible cité dans toutes les critiques de reproductibilité |
| BLOOM / OLMo (AI2) | publics | données et logs d'entraînement publiés | cités comme référence « recherche ouverte », repris par les audits académiques, mais niche par rapport à Llama/Mistral en usage final |

Conclusion empirique : la donnée d'entraînement pèse peu sur l'adoption grand public d'un
petit modèle, elle pèse sur le crédit auprès des chercheurs et des audits d'ouverture. Pour
steph, le public visé (utilisateurs malvoyants, intégrateurs, accessibilité) ressemble
davantage à celui de Llama/Mistral (poids + banc suffisent) qu'à celui d'un papier
académique.

### Ce que mesurent les labels d'ouverture

- **Open Source AI Definition (OSAID 1.0), OSI, octobre 2024** : n'exige pas la publication
  du jeu d'entraînement lui-même. Elle exige une « Data Information » suffisamment détaillée
  (provenance, traitement, comment l'obtenir ou l'obtenir sous licence) pour qu'une personne
  compétente puisse reconstruire un système substantiellement équivalent. L'OSI reconnaît
  explicitement que beaucoup de corpus ne peuvent pas être redistribués (PII, droits
  d'auteur, conditions de collecte) ; le sujet reste une priorité de gouvernance des données
  pour 2025-2026 ([Open Source AI Definition 1.0](https://opensource.org/ai/open-source-ai-definition), [OSI ne rend pas les données obligatoires](https://www.hpcwire.com/aiwire/2024/11/01/osi-open-ai-definition-stops-short-of-requiring-open-data/)).
- **Model Openness Framework (MOF), LF AI & Data / Generative AI Commons** : classe les
  modèles en trois niveaux. Le jeu de données brut n'entre qu'en **Classe I (Open Science)**,
  le niveau le plus exigeant et le plus rare ; la Classe III (Open Model) se contente des
  poids, de la carte de modèle et de la carte de données descriptive, sans le corpus brut
  ([MOF, arXiv](https://arxiv.org/pdf/2403.13784), [annonce LF AI & Data](https://lfaidata.foundation/blog/2024/04/17/introducing-the-model-openness-framework-promoting-completeness-and-openness-for-reproducibility-transparency-and-usability-in-ai/), [Model Openness Tool](https://isitopen.ai/)).
- **Stanford Foundation Model Transparency Index (FMTI), 2025** : le domaine « Data » est
  celui où les laboratoires sont le plus opaques (licences, PII, provenance), et le score
  moyen de transparence a reculé de 58/100 en 2024 à 40/100 en 2025. C'est une mesure faite
  sur les grands laboratoires, pas sur les petits projets communautaires, mais elle confirme
  que l'écart type de la profession est bas : publier la donnée met steph nettement au-dessus
  de la moyenne du secteur si le choix est fait ([FMTI décembre 2025](https://crfm.stanford.edu/fmti/December-2025), [Stanford Report](https://news.stanford.edu/stories/2025/12/foundation-model-transparency-index-ai-companies-information)).

## 2. Standards à suivre si publication

steph applique déjà, dans `benchmark/`, l'essentiel de l'outillage qu'une publication du
jeu d'entraînement demanderait. Il s'agit de dupliquer le même schéma, pas d'en inventer un.

| Standard | Déjà fait sur `benchmark/` | À faire sur le jeu d'entraînement |
|---|---|---|
| Carte de jeu de données Hugging Face (en-tête YAML + corps Markdown) | `benchmark/data/README.md` | même structure : `license`, `language`, `task_categories`, `pretty_name`, `size_categories` ([Dataset Cards, Hugging Face](https://huggingface.co/docs/hub/datasets-cards)) |
| Datasheets for Datasets (Gebru et al., motivation / composition / collecte / traitement / distribution) | suivi, référencé dans `benchmark/README.md` | même grille, en insistant sur la section « collecte » (machines réelles) et « éthique » (anonymisation) ([Datasheets for Datasets, arXiv](https://arxiv.org/abs/1803.09010)) |
| Croissant (MLCommons, JSON-LD sur schema.org) | `benchmark/data/croissant.json`, généré par `make_croissant.py` | générer l'équivalent pour le jeu d'entraînement ; Croissant est repris nativement par le visualiseur Hugging Face ([spécification Croissant](https://docs.mlcommons.org/croissant/docs/croissant-spec.html)) |
| Citation (`CITATION.cff`) | présent, format CFF 1.2 | ajouter une entrée `type: dataset` séparée ou une section dédiée |
| Versionnage immuable | `data/v1/`, corrections en `v2` | même politique : `train-v1/`, jamais de réécriture silencieuse d'une version publiée |
| Séparation train/validation/test | `compose_train.py` : hash SHA-256 du message utilisateur, split déterministe 95/5 | déjà fait ; documenter la méthode dans la carte (déterminisme, pas de fuite) |
| Lien avec la carte du modèle | à faire (A10, publication du GGUF) | la carte HF du modèle affiné doit pointer vers la carte du jeu de données et réciproquement (pratique attendue par la communauté) |
| Lien avec le benchmark, contamination | déjà vérifié : `tools/check_contamination.py`, 0 cas contaminé, 3 cas déplacés en `dev` avant publication (`benchmark/README.md`, section Contamination) | republier ce même résultat dans la carte du jeu d'entraînement, dans le sens inverse (le jeu d'entraînement ne contient aucune sortie ni chaîne canari du banc) |
| Canary string anti-contamination | présent dans chaque cas du banc | vérifier, à la publication, qu'aucune ligne du jeu d'entraînement ne contient la chaîne canari `termspeak-canary-v1-...` |

Le point de vigilance propre à ce jeu, absent du benchmark : le format d'entraînement est
`{"messages": [...]}` (format chat OpenAI), pas le format `cmd/output/expected` du banc. La
carte de jeu de données doit documenter ce format et le lien exact avec `label.py` et
`src/steph/digest.py` / `src/steph/prompts.py`, pour qu'une personne tierce puisse
reconstruire le même pipeline de prompts.

## 3. Licence

### Compatibilité de la source

- **Qwen3.5 9B (enseignant)** : licence Apache 2.0 stricte, vérifiée sur le fichier LICENSE
  d'un modèle Qwen3.5 de la même famille. Pas de clause Tongyi Qianwen ni de restriction sur
  l'usage des sorties du modèle (contrairement à certains modèles Qwen antérieurs de très
  grande taille) : les textes générés par Qwen3.5 peuvent être réutilisés, y compris pour
  entraîner un autre modèle et à des fins commerciales ([licence Qwen3.5-35B-A3B, Hugging Face](https://huggingface.co/Qwen/Qwen3.5-35B-A3B/blob/main/LICENSE)). Aucun verrou légal de ce
  côté.
- **Sorties d'outils tiers dans le corpus** (git, apt, docker, systemctl, lspci...) : ce sont
  des faits bruts (chiffres, chemins, messages d'erreur), pas des œuvres de l'esprit
  protégeables en tant que telles dans la plupart des juridictions. Le risque n'est pas la
  propriété intellectuelle de ces outils mais la fuite d'identifiants réels qu'ils
  contiennent : c'est le rôle d'`audit_pii.py` / `clean_pii.py`, déjà en place.

### Options de licence pour le jeu de données

| Licence | Nature | Compatible Apache 2.0 (Qwen) | Effet sur la licence commerciale PolyForm NC de steph |
|---|---|---|---|
| **CC BY 4.0** (même licence que `benchmark/data/`) | permissive, attribution seule | oui | une entreprise peut réutiliser gratuitement le jeu de données pour entraîner *son propre* modèle commercial, y compris concurrent ; la licence PolyForm NC du **code** de steph reste intacte, elle ne porte pas sur les données |
| **CC BY-NC 4.0** | attribution, usage commercial interdit | oui | aligne la donnée sur le modèle commercial de steph (gratuit non commercial, payant sinon) ; mais « non commercial » est notoirement ambigu en droit (une entreprise qui l'utilise en interne pour un outil non vendu est-elle « commerciale » ?) et incompatible avec des mandats académiques (Plan S, Horizon Europe exigent CC BY) ([comparatif CC BY vs CC BY-NC](https://www.ep-journals.org/comparisons/cc-by-vs-cc-by-nc)) |
| **ODC-BY 1.0** | attribution, pensée pour les bases de données (droits sui generis) | oui | équivalent fonctionnel à CC BY 4.0 pour ce cas d'usage (CC 4.0 couvre déjà les droits de base de données) ; peu d'avantage pratique par rapport à CC BY 4.0 aujourd'hui |
| **CDLA-Permissive-2.0** (Linux Foundation) | permissive, pensée spécifiquement pour l'IA/ML | oui | ne pose aucune obligation sur les résultats obtenus par calcul sur la donnée (donc sur un modèle entraîné dessus) ; plus courte et plus lisible que CC BY, mais moins connue hors du monde ML ([FAQ CDLA-Permissive-2.0](https://github.com/Community-Data-License-Agreements/Releases/blob/main/CDLA-Permissive-2.0-FAQ.md)) |
| **Même licence que le code (PolyForm Noncommercial 1.0.0)** | non commerciale, avec licence payante séparée | oui, Apache 2.0 le permet | cohérent avec le modèle économique de steph : une entreprise qui veut le jeu de données à des fins commerciales doit payer, exactement comme pour le code ; mais peu lisible pour la communauté ML habituée aux licences data standard, et PolyForm est une licence de logiciel, pas conçue pour des données |

**Recommandation de licence, si publication** : CC BY-NC 4.0 ou PolyForm Noncommercial
(même licence que le code) sont les deux seules options qui protègent le modèle commercial de
steph. CC BY 4.0 et ODC-BY ouvrent la porte à une réutilisation commerciale gratuite par un
concurrent, ce qui contredit directement la raison d'être de la licence payante de steph.
CDLA-Permissive-2.0 a le même défaut que CC BY pour ce cas précis (pas de clause non
commerciale possible dans la version Permissive).

## 4. Risques

| Risque | Pratique déjà en place | Ce qu'il resterait à faire pour publier |
|---|---|---|
| PII résiduelle malgré l'audit | `audit_pii.py` scanne MAC, UUID, IP publiques/privées, e-mails, chemins `/home`, secrets, domaines privés, noms connus (liste hors dépôt) ; `clean_pii.py` corrige ; `finalize_labels.py` élimine toute ligne encore signalée avant `final/` | avant publication : audit indépendant par une deuxième personne (pas l'auteur des scripts), publication d'un contact et d'une procédure de retrait sur demande, comme le pratique la communauté (« redress and removal » documenté par Hugging Face) ([bonnes pratiques de retrait](https://knowingmachines.org/knowing-legal-machines/legal-explainer/questions/can-i-remove-my-personal-data-from-genai-training-datasets)) |
| Exposition de l'infrastructure de test | noms de machine, IP de LAN et VPN déjà remappés vers des plages privées ou de documentation (`192.0.2.0/24`, `2001:db8::/32`) par `clean_pii.py` ; scanner à 0 avant tout transfert (invariant du suivi de mission) | rien de plus si le scanner reste à 0 à la publication ; revérifier après toute modification des scripts |
| Concurrence qui réutilise les données | le format `{"messages": [...]}` est directement utilisable par n'importe quel pipeline LoRA/QLoRA standard : la barrière technique est nulle | seule la licence protège ici (voir section 3) ; une licence CC BY-NC ou PolyForm ferme cet usage sans démarche technique supplémentaire |
| Incident plateforme (hors du contrôle de steph) | aucun | Hugging Face a subi une intrusion en juillet 2026 touchant des jeux de données internes non publics de clients spécifiques ; les jeux de données publics n'ont pas été altérés selon l'entreprise. Risque résiduel faible pour un jeu public, mais à mentionner car c'est un fait récent et vérifiable ([confirmation Hugging Face](https://techcrunch.com/2026/07/20/hugging-face-confirms-breach-affected-internal-datasets-and-credentials-urges-users-to-take-action/), [divulgation officielle](https://huggingface.co/blog/security-incident-july-2026)) |

## 5. Hébergement

| Option | Avantages | Limites |
|---|---|---|
| **Hugging Face Datasets** | standard de facto du secteur pour ce type de corpus ; visualiseur intégré, cartes YAML rendues nativement, intégration directe avec `datasets` et Croissant, découverte par les mêmes personnes qui chercheront le GGUF affiné (A10) | pas de préservation à très long terme garantie contractuellement ; dépend d'une plateforme tierce |
| **Dépôt GitHub séparé** | contrôle total, versionnage Git natif, cohérent avec le hameçonnage déjà fait pour `benchmark/` (dépôt public dérivé) | aucune découverte par la communauté ML (pas de visualiseur, pas d'indexation par `datasets`) ; à réserver en complément, pas en remplacement |
| **Zenodo (DOI)** | DOI pérenne, citation académique formelle, archivage CERN à long terme, gratuit | pas d'intégration ML directe (pas de chargement natif comme `datasets`), moins visible pour un développeur qui cherche un jeu d'entraînement |
| **Dans le dépôt steph** | zéro infrastructure supplémentaire | le dépôt steph est sous licence code (PolyForm NC) : mélanger une donnée sous licence différente dans le même dépôt exige une clarté totale par dossier (comme déjà fait pour `benchmark/LICENSE-CODE` / `LICENSE-DATA`) ; le corpus est actuellement ignoré par git (`.gitignore`), l'y faire entrer est un choix structurant, pas un détail |

**Recommandation d'hébergement, si publication** : Hugging Face Datasets en hébergement
principal (découverte, standard, cohérent avec la publication prévue du GGUF en A10), Zenodo
en complément pour le DOI de citation académique. Pas dans le dépôt `steph` lui-même : le
corpus est actuellement hors git par choix explicite, et le mélanger changerait cet
invariant sans bénéfice (aucune intégration `datasets` ni visualiseur sur un simple dossier
GitHub).

## Sources

- [Open Source AI Definition 1.0, OSI](https://opensource.org/ai/open-source-ai-definition)
- [OSI Open AI Definition Stops Short of Requiring Open Data, AIwire](https://www.hpcwire.com/aiwire/2024/11/01/osi-open-ai-definition-stops-short-of-requiring-open-data/)
- [The Model Openness Framework, arXiv](https://arxiv.org/pdf/2403.13784)
- [Introducing the Model Openness Framework, LF AI & Data](https://lfaidata.foundation/blog/2024/04/17/introducing-the-model-openness-framework-promoting-completeness-and-openness-for-reproducibility-transparency-and-usability-in-ai/)
- [Model Openness Tool](https://isitopen.ai/)
- [The 2025 Foundation Model Transparency Index, Stanford CRFM](https://crfm.stanford.edu/fmti/December-2025)
- [Transparency in AI is on the decline, Stanford Report](https://news.stanford.edu/stories/2025/12/foundation-model-transparency-index-ai-companies-information)
- [Dataset Cards, Hugging Face](https://huggingface.co/docs/hub/datasets-cards)
- [Datasheets for Datasets, Gebru et al., arXiv](https://arxiv.org/abs/1803.09010)
- [Croissant Format Specification, MLCommons](https://docs.mlcommons.org/croissant/docs/croissant-spec.html)
- [Licence Qwen3.5-35B-A3B, Hugging Face](https://huggingface.co/Qwen/Qwen3.5-35B-A3B/blob/main/LICENSE)
- [CC BY 4.0 vs CC BY-NC, comparatif](https://www.ep-journals.org/comparisons/cc-by-vs-cc-by-nc)
- [FAQ CDLA-Permissive-2.0, Community Data License Agreements](https://github.com/Community-Data-License-Agreements/Releases/blob/main/CDLA-Permissive-2.0-FAQ.md)
- [Retrait de données personnelles d'un jeu d'entraînement, Knowing Machines](https://knowingmachines.org/knowing-legal-machines/legal-explainer/questions/can-i-remove-my-personal-data-from-genai-training-datasets)
- [Confirmation de l'incident de sécurité Hugging Face, TechCrunch](https://techcrunch.com/2026/07/20/hugging-face-confirms-breach-affected-internal-datasets-and-credentials-urges-users-to-take-action/)
- [Divulgation officielle de l'incident, Hugging Face](https://huggingface.co/blog/security-incident-july-2026)
- [Mini-Giants: "Small" Language Models and Open Source Win-Win, arXiv](https://arxiv.org/pdf/2307.08189)
- [État des modèles à poids ouverts 2026, Kingy AI](https://kingy.ai/blog/state-of-open-weight-ai-models/)

## Fichiers du dépôt consultés

- `bench/matrix/finetune/README.md`, `audit_pii.py`, `clean_pii.py`, `compose_train.py`, `finalize_labels.py`
- le journal de mission interne (non publié)
- `benchmark/README.md`, `benchmark/CITATION.cff`, `benchmark/LICENSE-CODE`, `benchmark/LICENSE-DATA`
- `LICENSE.md`, `NOTICE` (racine du dépôt steph)

Le jeu d'entraînement lui-même (`bench/matrix/finetune/labeled/`, ignoré par git) n'a pas
été lu ni copié pour cette recherche, conformément à la consigne.
