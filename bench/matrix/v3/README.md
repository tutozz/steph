# Banc v3

Banc d'évaluation de steph-speak : **1 083 sorties de commandes et sessions distinctes**, chacune évaluée avec le prompt de production français et anglais, soit **2 166 évaluations** (702 après X4, plus 381 cas des lots L14 et L15 de X2b).
Conception et règles : `DESIGN.md`. Schéma d'un cas : `schema.json`.
Le banc de 36 cas (`facts.v2.json`) et le Steph Speak Bench public (`benchmark/`) restent intacts.

**Ne jamais entraîner sur ce banc.** Chaque cas porte la chaîne canari de `schema.json` ; tout constructeur de corpus filtre la canari et `fingerprints.txt`.
Le split `test` ne se montre à aucun agent qui entraîne, étiquette, compose un corpus ou écrit des exemples.

## Contenu

| Fichier | Rôle |
|---|---|
| `cases/L01.jsonl` à `cases/L15.jsonl` | lots de capture relus : **source de vérité**, on corrige un cas ici ; L14 sorties longues, L15 locale `fr_FR.UTF-8` (X2b) |
| `cases/dev/<famille>.jsonl`, `cases/test/<famille>.jsonl` | banc assemblé par `tools/assemble.py`, ne pas éditer à la main |
| `harness/dev.json`, `harness/test.json` | cas au format de `bench_run.py` : une ligne par cas et par langue, id `<cas>@fr` ou `<cas>@en` |
| `harness/pre-l5/` | harnais d'avant L5, sans bloc de faits : `dev.json`, `test.json` (affiné), `dev.generic.json`, `test.generic.json` (générique) ; reproduisent X3, D5 et tout résultat antérieur au 2026-09-29 |
| `fingerprints.txt` | empreintes v3-fp1 des sorties, pour filtrer les corpus |
| `assembly.json` | tailles, répartitions, cibles, cas écartés |
| `leak/*.json` | contrôle de fuite final par corpus : ids et scores seulement |
| `calibration/` | K3-a DPO et P17 sur le split dev, verdicts du juge, puissance |

Outils (`tools/`) :

| Outil | Usage |
|---|---|
| `assemble.py --leak leak/*.json` | valide, écarte, répartit, écrit `cases/dev`, `cases/test`, `harness/`, `fingerprints.txt`, `assembly.json` |
| `validate.py <jsonl>` | schéma, entrée identique à `src/steph` au HEAD, regex, référence à 100 % en FR et EN |
| `audit_v3.py <jsonl>` | règles d'`audit_pii.py` sur **toutes** les chaînes d'un cas, historiques des questions compris |
| `leak_check.py prints / scan / local` | contrôle v3-fp1 par empreintes ; `scan` tourne sur l'hôte du corpus |
| `score_v3.py [--split] [--spoken] [--reaches-model] <run.json>` | qualité v3 d'un résultat de `bench_run.py`, par langue et par famille |
| `judge_v3.py <harness> <out> <run.json>...` | juge A7 en 2 passes sur un résultat v3 (pendant de `judge_bench.py`) |
| `judge_validate_v3.py build / run` | revalidation du juge : C1-C6 en français et 6 contrôles anglais sur des contextes v3 réels |
| `power_v3.py --a ... --b ... --judge ...` | bootstrap apparié par cas et écart minimal détectable |

Lancer un modèle sur le banc (même harnais que `bench_compact.sh`) :

```
for sd in 7 42 123; do
  python3 bench/matrix/bench_run.py --server <llama-server> --model <gguf> --label <m>-v3dev-b$sd \
    --cases bench/matrix/v3/harness/dev.json --maxc 0 --port 8960 --ngl 99 --payload "{\"seed\": $sd}" --out <m>-b$sd.json
done
python3 bench/matrix/v3/tools/score_v3.py --split dev <m>-b7.json <m>-b42.json <m>-b123.json
```

## Harnais et empreintes

Depuis le 2026-09-29, résumés du banc avec le bloc de faits L5, comme `narrator.py` (`tools/test_l5_production.py` compare chaque entrée de résumé dev à celle que `Narrator._finish` passe au modèle, profils affiné et générique).
Régénération : `tools/build_inputs.py cases/L*.jsonl cases/dev/*.jsonl cases/test/*.jsonl`, puis `tools/facts_harness.py finetuned <split> harness/pre-l5/<split>.json harness/<split>.json`.
Seules les entrées de résumé changent : 454 cas du banc sur 968 résumés reçoivent un bloc (462 dans les lots, cas écartés compris), soit 352 lignes sur 768 du harnais dev et 556 sur 1 168 du test. Faits, références, sorties, `reaches_model` et questions inchangés ; `input.builder.steph_commit` passe à `20cfa0d`.

| Harnais | sha256 | Contenu |
|---|---|---|
| `harness/dev.json` | `8c686025b219e08d1b0eee113b22c7662fbc06f2659b3ddb02742d5bdd3422da` | affiné, L5 |
| `harness/test.json` | `705fdcb9e5784e7dc80996780e83d5763f313f7d9bf5da435a2cd30dfbe2ad3f` | affiné, L5 |
| `generic_harness.py dev` | `e96d54d4f9017880e5704654124f60e022a3520933f63bda012862132a352654` | générique, L5, non stocké |
| `generic_harness.py test` | `8d90a662aac4cf249dabe3952d15c13c88f46c8328cc8b435e0e0f7f367d38a7` | générique, L5, non stocké |
| `harness/pre-l5/dev.json` | `1b8f7402f6bec18e105fa473e4b2a60d601f76a86f78580f5e74ca6457efaa26` | affiné, avant L5 |
| `harness/pre-l5/test.json` | `a463f8bf4a3e6b428b8ec2b9d083c02393e33fa5db1309297b2a465c647adbce` | affiné, avant L5 |
| `harness/pre-l5/dev.generic.json` | `247b1141816d2a11df6c46682d3af9197f87651195db380ac22c839526117fb5` | générique, avant L5 |
| `harness/pre-l5/test.generic.json` | `e4abce1c3aa4bfbb4f7fd2c8e3797e8aa648a2c61c5c09122aa92eaf402c8fab` | générique, avant L5 |

Un résultat se note avec le harnais qui l'a produit : `score_production.py --harness` et `judge_v3.py` lisent l'entrée du modèle dans le harnais, et le garde-fou d'ancrage rejoué accepte les mots du bloc de faits.

## Tailles

| Split | Cas | Évaluations (FR + EN) | Résumés | Questions |
|---|---:|---:|---:|---:|
| dev | 429 | 858 | 384 | 45 |
| test | 654 | 1 308 | 584 | 70 |
| **Total** | **1 083** | **2 166** | **968** | **115** |

Par famille (cible de `DESIGN.md`, section 3) :

| Famille | Cas | dev | test | Cible | Écart |
|---|---:|---:|---:|---:|---:|
| tests | 121 | 48 | 73 | 40 | +81 |
| history-qa | 115 | 45 | 70 | 90 | +25 |
| build-native | 102 | 41 | 61 | 30 | +72 |
| files | 90 | 34 | 56 | 40 | +50 |
| shell-scripts | 81 | 32 | 49 | 15 | +66 |
| packages-system | 80 | 32 | 48 | 30 | +50 |
| python | 51 | 21 | 30 | 30 | +21 |
| vcs-git | 48 | 19 | 29 | 40 | +8 |
| network-transfer | 44 | 17 | 27 | 25 | +19 |
| lint-format | 42 | 17 | 25 | 20 | +22 |
| disk-memory | 37 | 14 | 23 | 25 | +12 |
| js-node | 36 | 15 | 21 | 30 | +6 |
| network | 32 | 12 | 20 | 30 | +2 |
| services-logs | 31 | 12 | 19 | 30 | +1 |
| permissions-users | 28 | 12 | 16 | 12 | +16 |
| containers | 27 | 10 | 17 | 30 | **-3** |
| processes | 27 | 11 | 16 | 20 | +7 |
| data | 26 | 11 | 15 | 20 | +6 |
| hardware-system | 26 | 10 | 16 | 15 | +11 |
| rust-go | 25 | 10 | 15 | 20 | +5 |
| infra | 14 | 6 | 8 | 8 | +6 |

Plafond de `DESIGN.md` (10 % par famille, 108 cas) : `tests` le dépasse (121, 11,2 %) ; `build-native` 102 et `shell-scripts` 81 restent dessous.

Répartitions transverses (résumés seuls, 968 cas, sauf OS) :

| Axe | Observé | Avant X2b (594 résumés) | Cible | Manque |
|---|---|---|---|---|
| OS (1 083 cas) | Linux 67,1 %, macOS 32,9 % | macOS 36,2 % | 60 / 40 | **macOS -7,1 pts** (L15 capturé sous Linux seul) |
| Langue de la sortie | EN 65,8 %, **FR 25,5 %**, mixte 4,3 %, sans texte 4,3 % | FR 14,3 % | FR ≥ 25 %, EN 65 %, sans texte 10 % | sans texte -5,7 pts |
| Statut | échec 54,3 %, succès 45,4 %, interrompu 0,3 % | échec 55,7 % | 45 à 55 % chacun | aucun |
| Longueur | court 36,9 %, moyen 27,3 %, **long 35,8 %** | long 7,9 % | 30 / 35 / 35 | moyen -7,7 pts |
| Difficulté | facile 23,8 %, moyen 49,6 %, difficile 26,7 % | difficile 19,4 % | 25 / 45 / 30 | difficiles -3,3 pts |
| Origine (résumés) | réelle 99,3 %, reconstruite 0,7 % | réelle 99,0 % | réelle ≥ 80 % | aucun |
| Questions | 84 réponses présentes, 31 absentes | inchangé | un tiers d'absentes | 27 % d'absentes |

Machines : a1000-sandbox 603 cas, macOS HOME temporaire 356, i5 117, reconstruits publics 7.

## Règles

- **Entrée de production** : `digest()` plafonné à 587 caractères, sinon `compact_output`, puis `finetuned_summary_messages` (`TRAIN_SYSTEM` FR et EN) avec le bloc de faits L5 (`digest.extract_facts` sur la sortie brute, `facts_block` actif en production depuis `20cfa0d`). `validate.py` régénère les 1 188 entrées de résumé depuis `src/steph` au HEAD : **identiques à 100 %**. Questions (X4, format P20) : `[QA_SYSTEM, « Historique de la session :\n{ctx} », accusé « Compris, j'ai l'historique. », « (dossier actuel : {cwd})\n{question} »]`, `ctx` construit par la `Session` de steph remplie commande par commande (blocs de 2 500 caractères, budget 8 000, coupe des blocs anciens au fil de l'eau) ; `tools/build_inputs.py` régénère les 116 entrées, `validate.py` les compare à `src/steph` au HEAD : **identiques à 100 %**. Écart avec l'ancienne entrée : accusé et dossier ajoutés partout ; `v3-history-qa-0052` et `0053` gardent 3 blocs omis au lieu de 4. Faits et références inchangés.
- **Score** (`score_v3.py`, testé par `test_score_v3.py`) : même règle que `rescore.score_case`, faits de la langue du prompt, lus aussi sur deux vues de la réponse : nombres en lettres mis en chiffres, formules d'absence ramenées à « introuvable / not found » (X5). 0 si un interdit global (`facts.v2.json`) ou un interdit du cas apparaît ; sinon part des faits requis ; x0,8 au-delà de `max_words` (20 en résumé, 30 en question).
- **Faits** : relus par un relecteur adverse dans les 15 lots. L13 est relu en entier depuis X2b : 42 des 71 questions restantes avaient un défaut (59 %), surtout une formule d'absence trop stricte, élargie aussi sur les 11 questions d'absence déjà relues. L14 et L15 : seconde lecture sceptique de chaque cas par un agent distinct de l'auteur, 312 cas sur 400 relus avec au moins un défaut (78 %), tous corrigés ou écartés. Le champ `review.second_reader` manque encore sur L02, L07 et L11 (129 cas). Deux cas contestés : `v3-history-qa-0049` et `v3-hardware-system-0025` (langue de sortie de `lsmod`).
- **Split** : celui des lots, stratifié par famille (part dev entre 37 et 43 % par famille), une capture ou une session restent dans le même split. `assemble.py` refuse une part dev hors 30-50 % ou un `case_ref` d'un autre split.
- **Doublons** : aucune paire de résumés à Jaccard de lignes ≥ 0,7. Seize paires de questions partagent la même session avec une autre question : gardées, ce sont deux cas distincts.
- **Fuite** (`leak_check.py`, méthode v3-fp1) : 14 516 exemples de `rtx3080-final`, 3 323 de `a1000-k3-mix`, 666 du Speak Bench v1 et du banc 36, comparés sur place. **1 cas écarté** (`v3-containers-0001`, même commande `docker inspect` et Jaccard de lignes 0,33). Maximum restant : Jaccard de lignes 0,43, shingles 0,54. Canari trouvée dans aucun corpus.
- **Fuite, contrôle X4** (2026-09-28, même méthode, empreintes calculées sur l'hôte de chaque corpus) : corpus R1 et K3 (3080 : `mix-i1`, `mix-extra`, paires DPO, questions, fonctionnalités EN, détail K3, mélanges R2-C2 ; A1000 : `k3/mix`, `r1/mix-halfdetail`), `data/final` de serveur Xeon, T7 complet (tldr, 1 164 exemples bruts et étiquetés), R2-C4 parties 1 à 3 (3060 et dépôt). **8 cas écartés, tous par T7** : `v3-build-native-0007`, `v3-tests-0007`, `v3-packages-system-0011`, `v3-services-logs-0010`, `v3-hardware-system-0009`, `v3-containers-0014`, `v3-files-0011`, `v3-history-qa-0011` (messages d'erreur canoniques identiques ; le dernier est un artefact de chiffres normalisés, écarté par la règle). Les 438 exemples T7 retenus par R2-C2 (`t7_ok`) étaient déjà filtrés : aucun modèle entraîné ne les a vus. R2-C4 et les autres corpus : 0 nouveau cas. Canari : 0 partout. Résultats : `leak/*.json`.
- **Fuite, lots L14 et L15** (X2b, même méthode, empreintes calculées sur chaque hôte, corpus jamais déplacés) : RTX 3080 (`data/final`, R1 `mix-i1` et `mix-extra`, questions filtrées, fonctionnalités EN, détail K3, paires DPO K3 et R1, `t7_ok`, paires R2-C1 : 25 899 exemples), serveur Xeon `data/final` (11 042), portable A1000 `k3/mix` et `r1/mix-halfdetail` (6 350), T7 et R2-C4 partie 2 du dépôt (1 952), Speak Bench v1 et banc 36 (666). **13 cas écartés** sur 395, surtout des `apt-get -s` et des messages de permission canoniques. Corpus R2-C4 de RTX 3060 non retrouvé, donc non recomparé pour ces lots. Canari : 0 partout. Résultats : `leak/x2b-*.json`.
- **Anonymisation** : `audit_pii.py` à 0 sur les 710 cas, et `audit_v3.py` à 0 sur toutes les chaînes imbriquées. Échantillon relu à la main à l'assemblage : 8 cas tirés au hasard, rien trouvé.

## Puissance statistique

Calibration : champion K3-a DPO (`c0fd7afd…6914`) contre P17 (`d548f3fc…5c89`), GGUF Q4_K_M copiés depuis la machine d'entraînement, hachages vérifiés.
Split dev (283 cas, 566 évaluations), 3 graines de banc (7, 42, 123), harnais `bench_run.py` (température 0,2, top_p 0,9), `llama-server` Metal sur Mac M3 Pro, les deux modèles dans la même session.
Méthode de T5 (`tools/power_v3.py`) : bootstrap apparié par cas, 10 000 tirages ; l'unité est le cas (moyenne des graines puis des deux langues), puisque les réponses FR et EN portent sur la même sortie.
MDE = (z0,975 + z0,80) x écart type des différences par cas / racine(n).

Qualité v3 (`score_v3.py`, split dev) :

| Modèle | Graine 7 | Graine 42 | Graine 123 | FR | EN | Résumés | Questions |
|---|---:|---:|---:|---:|---:|---:|---:|
| K3-a DPO | 54,5 | 55,3 | 55,1 | 51,6 | 58,4 | 57,6 | 41,5 |
| P17 | 55,3 | 54,5 | 54,2 | 53,8 | 55,6 | 56,4 | 45,6 |

Écart minimal détectable en qualité (alpha 0,05 bilatéral, puissance 80 %) :

| Mesure | Banc 36 (T5) | v3 dev (283) | v3 test (427) | v3 complet (710) |
|---|---:|---:|---:|---:|
| Qualité, FR et EN, sd par cas 24,3 pts | 14,4 pts | 4,1 | 3,3 | **2,6** |
| Qualité, prompt FR seul (sd 31,5) | 14,4 | 5,2 | 4,3 | 3,3 |
| Qualité, prompt EN seul (sd 33,6) | - | 5,6 | 4,6 | 3,5 |
| Qualité, réponses que steph envoie vraiment au modèle (60 % des cas, sd 26,9) | - | 5,8 | 4,7 | 3,7 |
| Bruit des graines seul, même modèle, banc figé | 5,5 | 1,1 à 1,3 | 0,9 à 1,1 | 0,7 à 0,9 |

Projection après X2b, non mesurée (même écart type par cas, aucun modèle relancé : les GPU servent à X1) : MDE qualité 3,3 pts sur dev (429 cas), 2,7 sur test (654), **2,1 sur le banc complet (1 083)** ; inventions 4,5 %, 3,6 % et 2,8 %. Les cas L14 et L15, plus longs et plus difficiles, peuvent avoir un autre écart type : à remesurer avec `power_v3.py` au prochain passage des modèles sur dev.

K3-a contre P17 sur dev : **+0,3 pt, IC 95 % [-2,5 ; +3,2]**, signe p = 0,76 : égalité statistique, comme sur le banc 36.
Par langue : K3-a -2,2 pts en FR (IC [-5,8 ; +1,5]), +2,8 pts en EN (IC [-1,2 ; +6,7]) ; aucun des deux n'est établi.
Sur 283 cas dev, 26 donnent 0 aux deux modèles sur les 6 passes et 39 donnent 100 % : 23 % des cas ne départagent pas ces deux modèles.

Inventions au juge A7 (`tools/judge_v3.py`, 2 passes, verdict « invention » si les deux passes l'affirment), graine 42 seule, 566 réponses par modèle :

| Modèle | Inventions | Douteux | Refusés par le serveur |
|---|---:|---:|---:|
| K3-a DPO | 124 (22,1 %) | 30 | 4 |
| P17 | 114 (20,3 %) | 42 | 4 |

Les 8 refus (HTTP 400) sont les questions `v3-history-qa-0052` et `0053` : leur historique dépasse la fenêtre de 4 096 jetons par slot du serveur de juge partagé ; elles sont exclues du compte.
Inventions par langue du prompt : K3-a 82 en FR et 42 en EN ; P17 69 en FR et 45 en EN.

| Mesure, 1 graine | Banc 36 (T5) | v3 dev | v3 test | v3 complet |
|---|---:|---:|---:|---:|
| Écart minimal détectable, part des réponses inventées (sd par cas 33,2 pts) | 21,7 % (7,8 / 36) | 5,5 % | 4,5 % | **3,5 %** (1,3 / 36) |
| Idem, réponses que steph envoie au modèle | - | 7,5 % | 6,1 % | 4,7 % |

K3-a contre P17 : **+1,8 pt d'inventions, IC 95 % [-2,1 ; +5,7]**, signe p = 0,61 : égalité statistique.
Avec 3 graines, T5 divisait l'écart type des différences par 2,1 ; appliqué à v3, le MDE complet serait de l'ordre de 1,7 % des réponses. Estimation non mesurée : une seule graine a été jugée.

Juge revalidé avant la calibration, même serveur (3060, Qwen3.5-9B Q4_K_M, `judge_lib_a7.py` intact) : **C1-C6 en français 6/6 en passe A et en passe B, 6 contrôles anglais sur des contextes v3 réels 6/6 et 6/6** (`calibration/judge-validate-v3.json`).
Sur V3E6, le juge liste aussi `store.test.js`, présent dans le contexte, comme invention : verdict juste, liste trop longue.

## Validité du banc (X5)

Question de l'utilisateur : un score fait de faits en regex et de mots inclus note-t-il bien des réponses justes dites autrement, et la formulation ? Pas de panel humain. Tout est dans `x5/`.

**1. Robustesse du scoreur aux paraphrases.** Le Qwen3.5 27B (serveur Xeon, CPU) écrit, pour chaque évaluation (cas, langue), 5 reformulations justes de la référence et 5 phrases fausses plausibles (2 faits changés, 1 invention, 1 omission du fait clé, 1 contradiction). Il voit l'entrée et la référence, jamais les regex. Chaque phrase signalée (juste notée sous 100, fausse notée 100) est relue à la main : `reject` si le générateur s'est trompé d'étiquette, `secondary` si la phrase fausse ne change qu'un détail que les faits n'exigent pas (`audit.json`, `audit-holdout.json`). Seuls les cas dev sont lus.

| Mesure | Échantillon corrigé (159 évaluations, 1 588 phrases) avant | après | Hors échantillon (44 évaluations, 440 phrases) avant | règles génériques seules | après |
|---|---:|---:|---:|---:|---:|
| Faux négatifs (juste notée sous 100, longueur à part) | 28,5 % | 0,0 % | 29,2 % | **15,1 %** | 0,5 % |
| Faux positifs sur un fait exigé (changé ou omis) | 16,7 % | 0,0 % | 11,8 % | 11,8 % | 0,0 % |
| Faux positifs, inventions | 89,3 % | 96,9 % | 93,2 % | 93,2 % | 100 % |
| Faux positifs, contradictions | 59,5 % | 60,8 % | 63,6 % | 63,6 % | 63,6 % |
| Étiquettes du générateur écartées à la relecture | 108 (6,8 %) | | 24 (5,5 %) | | |

La colonne « hors échantillon » est l'estimation honnête pour les cas jamais corrigés, dont tout le split test : les corrections par cas ont été ajustées sur les phrases qu'elles notent, pas celles du hors échantillon.
Par langue, hors échantillon avant : faux négatifs EN 35,5 %, FR 22,9 % ; faits exigés faussés notés 100 : EN 9,5 %, FR 14,0 %. Résumés 31,3 %, questions 16,7 %.

Règles génériques ajoutées à `score_v3.py` (valent pour dev et test, sans lecture de réponses de modèle sur test) : nombres en lettres FR et EN lus en chiffres (« trente-six », « one hundred and five », « neuf virgule un », chiffres dits un à un), « pour cent » et « percent » en %, formules d'absence dites autrement (« absente », « lacks », « could not be located », « n'a pas été trouvé ») lues comme « introuvable / not found ». Faits corrigés : 80 cas de l'échantillon, 21 du hors échantillon (alternatives et interdits ciblés, jamais la sortie, l'entrée ni la référence : `apply_fixes.py` le refuse), et la formule d'absence des 31 questions sans réponse. `validate.py` : 1 105 cas, références à 100 %.

Limite de fond, mesurée : **un fait en regex ne voit ni une invention ajoutée ni une contradiction d'un détail non exigé** (93 à 100 % et 60 à 64 % notées 100). Le score de faits dit « le fait utile est-il là et juste », pas « la phrase est-elle entièrement vraie ». Les inventions relèvent du juge A7 (`judge_v3.py`), qu'il faut toujours lire à côté.

**2. Formulation à l'oral** (`tools/judge_style_v3.py`, testé par `test_judge_style_v3.py`). Juge 27B par paires sur la même entrée : clarté à l'écoute, fait utile en premier, concision, naturel, verdict global ; les deux ordres, verdict gardé s'il est stable, sinon égalité ; paires identiques égales sans appel. Il s'ajoute au score de faits.

| Contrôles plantés (`x5/controls.jsonl`, 80 paires, même faits) | Global | Concision | Naturel | Ordre | Clarté |
|---|---:|---:|---:|---:|---:|
| Pire construit : préambule, ligne de journal à symboles, phrase répétée (60) | **96,7 %** | 95,0 % | 86,7 % | 65,0 % | 23,3 % |
| Paires identiques, égalité attendue (20) | 100 % | 100 % | 100 % | 100 % | 100 % |
| Biais de position (part des verdicts bruts pour la réponse montrée en premier) | 49,6 % | 50,4 % | 52,6 % | 57,1 % | 75,4 % |

Seul le verdict **global** est retenu (≥ 90 % exigé) ; clarté et ordre ne passent pas, ils restent indicatifs.

Démonstration, v1.0 (`45414bd2…`) contre P17 (`d548f3fc…`), dev, graine 42, harnais aligné sur la production, CPU serveur Xeon : 720 paires sur 858 diffèrent, 240 tirées par hachage jugées (faute de temps de calcul : un 27B sur 12 cœurs, environ 26 s par paire).

| Verdict global | v1.0 préférée | P17 préférée | Égalité | Net v1.0 (IC 95 % bootstrap) |
|---|---:|---:|---:|---:|
| Tous (240) | 86 | 53 | 101 (dont 67 instables) | **+13,8 pts [+4,2 ; +23,3]** |
| Prompt FR (116) | 33 | 29 | 54 | +3,4 |
| Prompt EN (124) | 53 | 24 | 47 | +23,4 |

Même graine au score de faits : v1.0 50,5, P17 47,5. Biais de position sur ces paires réelles : 53,6 %.

**3. Température.** Production (`src/steph`) : résumés `temperature 0.2`, `top_p 0.9`, 90 jetons (`narrator._llm_say`, `LLM.stream`) ; questions `0.3`, `top_p 0.9`, 400 jetons (`server._ask`) ; aucun échantillonneur côté serveur. Le harnais envoyait 0,2 partout, 80 et 120 jetons. Il porte maintenant le `payload` de production par ligne (`v3lib.PRODUCTION_PAYLOAD`, gardé par `test_production_sampling.py`). Écart mesuré sur v1.0, questions dev, 3 graines : **+0,4 pt, IC [-0,9 ; +1,7]**, aucun effet établi. Écart non corrigé, hors échantillonnage : la production passe la réponse par `ground_stream` (garde-fou d'ancrage) avant de la dire, le banc note la sortie brute.

## Limites

| Limite | Effet | Ce qu'il faudrait |
|---|---|---|
| **48 % des évaluations de résumé ne vont jamais au modèle en production** (sortie vide, code 127, lecture telle quelle de 20 mots et 3 lignes, ou `resolve()`) | la note globale mesure aussi des sorties que steph dit sans modèle | lire aussi `score_v3.py --reaches-model` (338 évaluations sur 566 en dev) ; approximation de `narrator`, règles par commande ignorées |
| Répartition après X2b : macOS 32,9 % (cible 40 %), moyens 27,3 % (cible 35 %), difficiles 26,7 % (cible 30 %), `tests` à 11,2 % au-dessus du plafond de 10 % | le banc sur-pèse Linux et les suites de tests | un lot macOS de sorties moyennes |
| Lots L14 et L15 construits sur des bacs à sable synthétiques (scripts, projets et arbres générés, paquets GNU réels) : plusieurs sorties longues suivent un même gabarit (scripts français, suites de tests générées) | diversité moindre que des historiques réels | compléter par des sorties réelles d'usage quand elles existent |
| 36 cas `apt-get -s` : digest() coupe le total et `resolve()` répond sans modèle en production | ces cas ne mesurent que la simulation et le paquet visé | lire `--reaches-model` |
| Familles sous la cible : `containers` 28 sur 30, `network` 29 sur 30 ; `history-qa` 116 pour 90 | écart faible, sans effet sur la puissance | rien d'urgent |
| 23 % des cas dev ne départagent pas K3-a et P17 (tout à 0 ou tout à 100 %) | ils diluent la puissance entre modèles proches | les garder : ils départageront des modèles plus faibles ou plus forts |
| `review.second_reader` absent sur L02, L07, L11 (129 cas) | défaut de faits possible au taux observé ailleurs (59 à 78 % à la seconde lecture de L13 à L15) | relire L02, L07 et L11 |
| Faits jamais confrontés à de vraies sorties de modèle avant cette calibration | des faits trop stricts ou trop laxistes restent possibles | relire les cas où les deux modèles ont 0 sur toutes les graines (26 en dev) |
| Deux sessions sur la même histoire comptent pour deux cas (16 paires de questions) | légère corrélation, l'IC est un peu optimiste pour les questions | bootstrap par session si les questions deviennent décisives |
| Calibration sur Mac (Metal), une seule paire de modèles proches | le sd par cas vient d'une paire ; un autre harnais déplace le score (T5 : 2 pts) | recalculer `power_v3.py` à chaque nouvelle paire, dans la même session |
| `audit_pii.py` ne lit que les chaînes de premier niveau et `messages` | les historiques des questions échappaient à l'audit des lots | `audit_v3.py` couvre tout : 0 trouvaille |
| Inventions jugées sur une seule graine, verdicts jamais relus à la main sur v3 ; juge lancé en client du serveur A7 déjà chargé par la boucle (port 8933, 3 requêtes à la fois) faute de 3060 libre | MDE inventions à 3 graines seulement estimé ; charge partagée avec la boucle | juger les graines 7 et 123 ; relire 50 verdicts |
| Serveur de juge à 4 096 jetons par slot | 2 questions à long historique non jugées | serveur à fenêtre plus large pour le juge v3 |
| Fuite : comparaison par empreintes normalisées, pas sémantique | une reformulation d'une même sortie passerait | acceptable : les sorties du banc sont capturées après les corpus |
