# Carte de modèle : steph-speak v1.0

Carte finalisée à la dernière étape de la mission de réentraînement (le journal de mission interne (non publié)), à partir de ce
brouillon rédigé pendant la mise en conformité open source (`docs/open-source.md`, section
3.1, gabarit annoté Mitchell et al.). Miroir exact du `README.md` publié sur le dépôt
Hugging Face **privé**
`tutozz/steph-speak-granite-4.0-h-350M-dpo-v1-GGUF` (organisation cible `lsmdx` non créée
au 2026-09-28, voir Décisions ci-dessous) : toute modification de fond se fait dans les
deux fichiers à la fois. Aucune publication publique : seul le site steph.lsmdx.com est
public (consigne utilisateur, le journal de mission interne (non publié), invariants).

Le réentraînement final est fait : la base retenue est `ibm-granite/granite-4.0-h-350m`
(Qwen3.5-0.8B n'a pas été retenu). Les valeurs chiffrées ci-dessous viennent de
`bench/matrix/results/finetune/r1/r1-summary.json` et du journal de mission interne (non publié) ;
aucune n'est inventée. Ce qui reste non mesuré est listé dans « Non vérifié » en fin
de document, jamais tu.

## Dépôt Hugging Face

| Champ | Valeur |
|---|---|
| Identifiant | `tutozz/steph-speak-granite-4.0-h-350M-dpo-v1-GGUF` |
| Visibilité | privé |
| Espace de noms cible | `lsmdx/...` (décision documentée dans `docs/open-source.md`) ; transfert dès la création de l'organisation, non faite au 2026-09-28 |
| Fichier GGUF | `steph-speak-granite-4.0-h-350M-dpo-v1.0-Q4_K_M.gguf`, sha256 `45414bd2af2daf5fb9fbcb1ade078e6a2bb3cb3f341c8d0eb5fa8c3abb92ec5b` |
| Fichiers Ollama | `system` (prompt système d'entraînement), `Modelfile` |

## En-tête YAML (Hugging Face)

```yaml
license: apache-2.0
base_model: ibm-granite/granite-4.0-h-350m
base_model_relation: quantized
language:
  - fr
  - en
pipeline_tag: text-generation
library_name: gguf
tags:
  - accessibility
  - screen-reader
  - terminal
  - summarization
  - steph
  - gguf
  - llama.cpp
  - ollama
```

## Corps de la carte

### Description

steph-speak est un petit modèle de langage affiné pour résumer à voix haute la sortie
d'une commande de terminal, en une phrase courte, pour une personne aveugle ou
malvoyante. Il est le moteur de résumé du terminal parlant
[steph](https://github.com/tutozz/steph) (licence PolyForm Noncommercial, non couverte par
cette carte : le produit est protégé, le modèle est ouvert).

Cette version, **steph-speak v1.0**, est le modèle retenu du réentraînement final (décision
autonome du 2026-09-28, le journal de mission interne (non publié)) : la recette corrigée sur ses
points faibles (questions, anglais), réentraînée sur le corpus complet, le prompt et le
gabarit de production courants au 2026-09-27, puis interpolée à 70 % avec la version
précédente (le modèle de repli) sans réentraînement supplémentaire (`i2`, lambda SFT 0,7 —
seule valeur non inférieure à la version précédente selon la règle de décision documentée
dans le journal de mission interne (non publié)).

### Usage prévu

Résumé vocal d'une sortie de commande shell dans le pipeline steph : lecture de l'entrée
(commande, code de sortie, sortie brute), production d'une phrase de 15 mots au plus,
faits exacts, rien d'inventé.

### Usages hors périmètre

- Conseil de sécurité ou décision automatisée à partir d'une sortie de commande.
- Résumé de contenu hors terminal (texte libre, documents, conversations).
- Certification de sûreté d'un assistant : le modèle réduit le risque d'invention, il ne
  l'élimine pas (voir Limites).

### Limites

- Entraîné et évalué en français et en anglais ; c'est le premier modèle steph-speak
  entraîné aux fonctionnalités et aux questions en anglais (les versions précédentes
  n'avaient que le résumé en anglais).
- Couvre les sorties d'outils Linux et macOS courants (compilateurs, git, gestionnaires de
  paquets, réseau, disques, matériel, conteneurs) ; pas de Windows.
- Échec net sur la sous-catégorie de robustesse aux questions `qa0` : 0 % sur les 3 graines
  de test (corrige à tort « titel » en « Titl »), alors que la version précédente y obtient 100 %.
- Taux d'invention mesuré sur un **banc interne de 36 cas seulement** : preuve faible,
  intervalles de confiance larges (voir Évaluation). Un banc plus représentatif (v3) est en
  préparation (`bench/matrix/v3/`).
- Non significativement différent de la version précédente sur la métrique composite interne
  `v2` (intervalle de confiance à 95 % traversant zéro) ; elle reste le modèle de repli.
- Recette d'entraînement et de fusion susceptibles de rouvrir un nouveau réentraînement
  final si le prompt, le gabarit, le digest ou le corpus de production changent.

### Prompt système exact

Le modèle est affiné sur un prompt système court, différent du prompt système long de
Steph Speak Bench (`benchmark/data/v1/prompts.json`). Livré avec le GGUF : fichiers
`system` et `Modelfile` (Ollama).

Français (`bench/matrix/finetune/train_system_prompt.txt`, prompt par défaut du dépôt) :

```
Tu lis la sortie d'une commande de terminal et tu dis à voix haute l'essentiel, en français. Réponds par une seule ligne courte, 15 mots au plus : d'abord le résultat, puis un détail utile. Recopie les noms et les nombres exactement comme dans la sortie. Si une information n'est pas écrite dans la sortie, ne la donne pas : n'invente jamais.
```

Anglais (`bench/matrix/finetune/train_system_prompt.en.txt`, sessions en langue anglaise) :

```
You read the output of a terminal command and say the essential aloud, in English. Answer with a single short line, 15 words at most: the result first, then one useful detail. Copy names and numbers exactly as they appear in the output. If a detail is not written in the output, do not give it: never invent.
```

### Recette d'entraînement

| Paramètre | Valeur |
|---|---|
| Base | `ibm-granite/granite-4.0-h-350m`, poids fusionnés (SFT + DPO) puis quantifiés |
| Départ des poids | reconstruction de la version précédente (base Granite + moyenne des 4 adaptateurs SFT + moyenne des 4 adaptateurs DPO), 402/402 tenseurs identiques à la version précédente avant le réentraînement final |
| Méthode | LoRA, rang 16, alpha 32, dropout 0,05, `all-linear` (Mamba inclus) |
| SFT | taux d'apprentissage 2e-4, 3 époques, 4 graines (42, 7, 123, 2024) |
| DPO (RPO, anti-invention) | taux d'apprentissage 2e-5, bêta 0,1, terme SFT poids 1,0, 4,29 époques, 60 pas, 223 paires (152 du mix du réentraînement final + 71 reprises de la version précédente) |
| Fusion | `merge_pref.py`, échelle SFT 0,7, échelle DPO 1,0, puis interpolation 70 % vers la version précédente (`i2`, sans réentraînement) |
| Corpus | 4 012 exemples d'entraînement, 216 de validation (mix du réentraînement final : résumés FR/EN, fonctionnalités FR/EN, questions FR/EN, cas de banc) ; jeu d'entraînement interne `steph-speak-train` (préparation faite en amont, licence CC BY 4.0 décidée, non encore publié) |
| Enseignant des étiquettes | `Qwen/Qwen3.5-9B` Q4_K_M, température 0 (Apache 2.0, aucune clause sur les sorties) |
| Quantification livrée | Q4_K_M |
| Environnement | llama.cpp b11205, PyTorch 2.11.0+cu128, Transformers 5.17.0, PEFT 0.21.0, safetensors 0.8.0, GPU d'entraînement RTX 3080 10 Go, pilote 610.43.02 |

Ce tableau documente l'état atteint dans le code (`bench/matrix/finetune/train_lora.py`,
`bench/matrix/finetune/pref/train_dpo.py`, `bench/matrix/finetune/loop/`) pour ce modèle
précis (steph-speak v1.0, issu du réentraînement final).

### Matériel et durée

GPU d'entraînement : RTX 3080 10 Go (pilote 610.43.02). Durée d'entraînement par graine et
lieu géographique non capturés (voir Non vérifié).

### Évaluation

Deux protocoles séparés (`benchmark/README.md`) : protocole standard (prompt système long
du banc) et protocole steph (prompt système d'entraînement court, `TRAIN_SYSTEM`).

#### Steph Speak Bench, split test (62 cas par langue)

Comparaison appariée contre la version précédente, protocole steph :

| Mesure | steph-speak v1.0 | Version précédente (repli) | Écart | IC95 % |
|---|---|---|---|---|
| FR | 44,8 | 38,5 | +6,3 pts | [-1,5 ; 14,6] |
| EN | 47,2 | 39,6 | +7,6 pts | [-1,3 ; 16,3] |

Non significatif (l'intervalle de confiance traverse zéro) mais dans le sens favorable au
modèle issu du réentraînement final sur les deux langues.

Scores bruts, protocole standard (pas de test statistique disponible pour ce protocole) :

| Mesure | steph-speak v1.0 | Version précédente (repli) |
|---|---|---|
| FR | 45,4 | 37,5 |
| EN | 49,4 | 44,3 |

#### Taux d'invention (banc interne, 36 cas, 3 graines de banc : 7, 42, 123)

**Avertissement : banc de 36 cas seulement, preuve faible.** À rejuger sur le banc v3
(en préparation, `bench/matrix/v3/`).

| Mesure | steph-speak v1.0 | Version précédente (repli) |
|---|---|---|
| Inventions/36 par graine | 5, 3, 4 (moyenne 4,0) | 5, 5, 6 (moyenne 5,3) |
| Inventions/36 vérifiées au sol (`ground truth`) | 4, 4, 3 (moyenne 3,7) | 4, 4, 5 (moyenne 4,3) |
| Robustesse aux questions `qa0` | 0/100 sur les 3 graines (échec net) | 100/100 |
| Robustesse aux questions `qa1`, `qa2` | 100/100 | 100/100 |

Comparaison appariée des inventions (3 graines) : 2 cas pires et 1 cas meilleur pour
steph-speak v1.0 sur les inventions brutes, test de signe non significatif (p = 1,0).

#### Métrique composite interne `v2` (banc de développement, non publique)

Utilisée par une règle de décision documentée dans le journal de mission interne (non publié) pour arbitrer entre
variantes pendant l'entraînement, distincte de Steph Speak Bench.

| Mesure | steph-speak v1.0 | Version précédente (repli) |
|---|---|---|
| `v2` | 84,5 | 87,7 |
| Écart | -3,2 pts, IC95 % [-11,1 ; 2,8] (non significatif, non-infériorité retenue) | - |
| `holdout` | 69,4 | 80,6 |
| `summary` | 86,1 | 86,6 |
| `spoken` | 87,2 | 90,5 |

#### Précision de la langue produite (classifieur trigramme)

Clés techniques telles qu'enregistrées dans `bench/matrix/results/finetune/r1/r1-summary.json`
(`lang`) ; l'association au protocole steph/standard est déduite par analogie avec le champ
`test` (`steph_fr`/`std_fr`), non documentée explicitement à la source.

| Clé | Valeur | Protocole déduit |
|---|---|---|
| `model-steph_fr_test` | 74,2 % | steph, FR |
| `model-steph_en_test` | 51,6 % | steph, EN |
| `model_fr_test` | 66,1 % | standard, FR |
| `model_en_test` | 59,7 % | standard, EN |

### Contamination

Procédure disponible (`benchmark/tools/check_contamination.py`, canari
`termspeak-canary-v1-5e0c83a1d7f2`, `data/v1` figé) mais **non rejouée spécifiquement sur
le corpus du réentraînement final** au 2026-09-28 : aucun résultat de contrôle propre à ce modèle n'a été trouvé
dans `bench/matrix/results/finetune/r1/`. À faire avant toute publication.

### Vitesse et mémoire (CPU, Intel i5-7200U, llama.cpp b11205)

Réglages : `-c 8192 --parallel 2 -b 512 -ub 512 -t 4 --cache-ram 0`, 36 cas, deux passes
répétées par modèle (plage min-max rapportée telle quelle, sans moyenne).

| Mesure | steph-speak v1.0 (2 passes) | Version précédente, repli (2 passes) |
|---|---|---|
| Temps au premier mot, médiane | 0,639-0,641 s | 0,594-0,633 s |
| Temps au premier mot, p90 | 1,394-1,406 s | 1,283-1,401 s |
| RAM crête | 544-545 Mo | 543-546 Mo |
| Débit de génération, médiane | 58,1-58,3 tokens/s | 57,9-61,1 tokens/s |

### Empreinte carbone

Non mesurée (écart connu, `docs/open-source.md` §16). Aucune valeur n'est avancée ici.

### Licence et attributions

- Poids de ce dépôt : **Apache 2.0** (même licence que la base, aucune obligation
  au-delà de la licence jointe et du signalement des fichiers modifiés).
- Base : `ibm-granite/granite-4.0-h-350m` (Apache 2.0).
- Enseignant des étiquettes : `Qwen/Qwen3.5-9B` (Apache 2.0, aucune clause sur l'usage des
  sorties pour l'entraînement).
- NOTICE : à compléter (fichier `NOTICE` hors périmètre de cette carte).
- Le produit steph (digest, prompt de résolution, garde-fou d'ancrage, intégration shell)
  reste sous licence PolyForm Noncommercial + licence commerciale ; il n'est pas couvert
  par cette carte.

### Usage

#### llama.cpp

```sh
llama-server -hf tutozz/steph-speak-granite-4.0-h-350M-dpo-v1-GGUF:Q4_K_M
```

Dépôt privé : authentification Hugging Face (`hf auth login` ou `HF_TOKEN`) avec un accès
autorisé nécessaire tant qu'il n'est pas rendu public.

#### Ollama

Avec le `Modelfile` fourni (GGUF téléchargé localement au préalable, dépôt privé) :

```sh
ollama create steph-speak -f Modelfile
ollama run steph-speak
```

Le fichier `system` contient le même prompt système, au format attendu par `hf.co/<dépôt>`
une fois le dépôt public (`docs/open-source.md`, section 3.7). Steph appelle lui-même le
modèle avec un `max_tokens` et une température qui varient selon le contexte (résumé court,
fin de commande longue) : voir `src/steph/llm.py` et `src/steph/narrator.py`, non figés
dans ce `Modelfile`.

#### steph

`steph` propose ce modèle par défaut dans `steph setup` une fois le dépôt rendu public ;
tant qu'il reste privé, le catalogue de steph le marque comme indisponible.

### Citation

À compléter avec un `CITATION.cff` une fois le dépôt public.

### Contact

Signalement d'une faille ou d'une donnée personnelle résiduelle : voir `SECURITY.md` du
dépôt [steph](https://github.com/tutozz/steph).

## Non vérifié

| Point | Raison |
|---|---|
| Durée d'entraînement par graine, lieu géographique | non capturés dans `bench/matrix/results/finetune/r1/r1-summary.json` ni ailleurs dans le dépôt |
| Empreinte carbone | jamais mesurée (écart 16 de `docs/open-source.md`) |
| Contrôle de contamination propre au corpus du réentraînement final | procédure existante, non rejouée sur ce corpus précis avant la rédaction de cette carte |
| Métadonnées GGUF (`general.license`, `general.base_model.*`) | non contrôlées (écart 17 de `docs/open-source.md`) |
| Association protocole steph/standard sur les clés `lang.model*` | déduite par analogie de nommage, non confirmée à la source |
| Propriétaire du compte HF `tutozz` | non vérifié (déjà noté dans `docs/open-source.md`) |
