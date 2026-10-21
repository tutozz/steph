# P20 : latence des questions (F7) sur l'i5

**Verdict.** Le 13 à 15 s prédit par R2-B1 existe, mais seulement à froid : question posée
avant que l'historique soit lu. En production, le préchauffage du slot 1 lit l'historique au
repos. Une question posée ensuite répond en **0,36 s au p90** sur l'i5, même à 3 000 jetons.
Levier retenu : **masquage en code**. Une phrase courte part tout de suite quand l'historique
n'est pas encore lu. L'entrée du modèle ne change pas, la qualité non plus. Défaut corrigé au
passage : un préchauffage interrompu passait pour fini et ne reprenait jamais.

## 1. Mesures d'entrée (banc v3, historique des questions)

Jetons comptés par le tokeniseur de R1 (`/apply-template` puis `/tokenize`), entrées du banc.

| Split | Évaluations | p50 | p90 | max |
|---|---:|---:|---:|---:|
| dev | 90 | 396 | 1 290 | 3 024 |
| test (entrées seulement, aucun score) | 140 | 392 | 973 | 1 725 |

Où est la réponse, dev, 45 questions FR (regex `need` du cas cherchées bloc par bloc) :

| Position | Questions |
|---|---:|
| dernier bloc | 12 |
| avant-dernier bloc | 8 |
| bloc plus ancien | 9 |
| aucune regex trouvée (réponse reformulée) | 5 |
| réponse absente par construction | 11 |

La question nomme une commande de l'historique dans **9 cas sur 34** seulement.

## 2. Leviers évalués

| Levier | Mesure | Verdict |
|---|---|---|
| Cache de préfixe existant (`_maybe_warm`) | i5 : 0053, 3 050 jetons, 14,7 s à froid, **0,28 s** après préchauffage ; bloc ajouté : 2 464 jetons repris sur 2 976 (point de reprise à `n - ub`) | **déjà actif**, c'est lui qui rend la production rapide |
| Plafond plus serré (4 000 ou 2 500 car. au lieu de 8 000) | Mac, 3 passes : moyenne 54,2 / 55,0 / 53,9 (bruit ±2,3) ; sur les 10 évaluations touchées : 5,94 contre 5,12 et 5,00 ; 0052 et 0053 tombent à 0 | **rejeté** : perd les réponses là où il agit, change le format que R2 apprend, froid encore 7 s |
| Sélection des blocs selon la question | 25 questions sur 34 ne nomment aucune commande ; 17 réponses hors du dernier bloc | **rejeté** : une entrée qui dépend de la question ne peut plus être préchauffée ; chaque question paierait une lecture à froid |
| Résumés déjà dits à la place des blocs anciens | non mesuré | **rejeté** : change le bloc quand il vieillit, donc casse le cache d'ajout seul ; format nouveau pour R2 |
| Masquage de l'attente | voir section 3 | **retenu** |
| Réglage llama-server | `-ub` réfuté (R2-B1) | hors périmètre |

## 3. Preuve sur l'i5

Machine vérifiée libre avant chaque passe (aucun `llama-server`, `piper`, juge ni boucle X1).
Une passe à la fois. i5-7200U, llama-server b11205, `-c 8192 --parallel 2 -b 512 -ub 512 -t 4
--cache-ram 0 --reasoning-budget 0 --jinja`, R1 v1.0 Q4_K_M sha256 `45414bd2…`. Seul ajout :
`--slot-save-path`, pour vider le slot 1 entre deux cas.

Harnais `bench/matrix/p20_qa_latency.py` : vraie `Session`, vrai `Narrator` (préchauffage),
vrai `ControlServer._ask` (ancrage compris), haut-parleur factice. « Premier son » = premier
morceau remis au haut-parleur, avant synthèse Piper. Code avant : `b8f9633`.

| Régime | Population | 1er jeton p90 avant | 1er jeton p90 après | 1er son p90 avant | 1er son p90 après |
|---|---|---:|---:|---:|---:|
| froid (slot vidé, aucun préchauffage) | 17 questions dev60 (R2-B1) | **12,81 s** | 12,90 s | 12,81 s | **0,01 s** |
| froid | 90 évaluations dev | 6,89 s | 6,95 s | 6,89 s | 0,01 s |
| préchauffé | 17 questions dev60 | **0,36 s** | 0,38 s | 0,36 s | 0,38 s |
| préchauffé | 90 évaluations dev | 0,38 s | 0,38 s | 0,38 s | 0,38 s |
| rejeu, question 2 s après la dernière commande | 17 questions dev60 | 1,66 s | 1,66 s | 1,66 s | **0,31 s** |
| rejeu, 2 s | 90 évaluations dev | 1,54 s | 1,53 s | 1,54 s | 0,36 s |

- Froid, max : 16,1 s avant, 16,2 s après. Le premier jeton ne bouge pas : l'entrée est identique.
- Phrase dite : 90 fois sur 90 à froid, 0 sur 90 préchauffé, 25 sur 90 au rejeu.
- Rejeu : aucune attente de plus de 0,6 s sans phrase ; 4 phrases pour une attente de 0,3 à 0,6 s
  (préchauffage fini pendant l'envoi).
- Phrase jamais présente dans le texte envoyé à la fenêtre ni dans `s.qa` : 0 sur 540 réponses.

## 4. Qualité des questions (score_v3, split dev, 90 évaluations)

Même modèle, température 0,3 du vrai chemin, sans graine : l'écart entre passes est du bruit.

| Machine | Avant | Après |
|---|---|---|
| i5, 3 passes (froid, préchauffé, rejeu) | 55,9 / 51,1 / 52,2, moyenne **53,1** | 50,7 / 53,9 / 54,4, moyenne **53,0** |
| Mac Metal, 3 passes à froid | 56,5 / 52,0 / 54,1, moyenne **54,2** | 53,7 / 53,9 / 57,0, moyenne **54,9** |

## 5. Ce que fait le code

| Fichier | Changement |
|---|---|
| `src/steph/server.py` | phrase `qa_wait` mise en tête du flux parlé si `Narrator.qa_wait_phrase` la demande ; jamais envoyée à la fenêtre, jamais gardée dans `s.qa` |
| `src/steph/narrator.py` | `_qa_cached` : préfixe lu sur le slot 1 (préchauffage fini ou réponse donnée) ; oublié au déchargement et au rechargement ; phrase si le préfixe diffère et si la lecture estimée dépasse la durée de la phrase (règle P9) |
| `src/steph/llm.py` | un flux de fond coupé avant `[DONE]` lève `ConnectionError` : le préchauffage interrompu reprend |
| `src/steph/strings.py`, `src/steph/tts.py` | « Je regarde l'historique. » / « Checking the history. », synthétisées d'avance (cache P19) |

Défaut trouvé : `abort_background()` ferme la socket, `http.client` finit la lecture sans
erreur, `complete()` renvoie `""`. Le narrateur croyait le préchauffage fini et ne le relançait
pas avant la commande suivante. Reproduit sur un llama-server réel (Mac, `{'out': ''}`).

## 6. Format d'entrée que R2 doit reproduire

Inchangé par P20. C'est celui de `Narrator.qa_messages()` plus la question, profil affiné :

```
[{"role": "system",    "content": QA_SYSTEM  (QA_SYSTEM_EN en anglais)},
 {"role": "user",      "content": "Historique de la session :\n{ctx}"   ("Session history:\n{ctx}")},
 {"role": "assistant", "content": "Compris, j'ai l'historique."         ("Understood, I have the history.")},
 # jusqu'à 4 échanges précédents : {"user": question brute}, {"assistant": réponse}
 {"role": "user",      "content": "(dossier actuel : {cwd})\n{question}"}]
```

- `ctx` = `Session.context(2500, 8000)` : blocs `[{id}] {cwd} $ {cmd}   (code {exit}, {durée} s, {n} lignes)`
  puis `compact_output(lignes, 2500)`, séparés par une ligne vide ; blocs anciens coupés par
  tiers au-delà de 8 000 caractères, avec la ligne `({n} commandes plus anciennes omises)`.
- Le préfixe « (dossier actuel : … ) » est en français dans les deux langues, comme la production.
- La phrase d'attente n'entre jamais dans l'entrée ni dans les échanges précédents.

Écarts relevés, à trancher pour R2 :

| Source | Écart avec la production |
|---|---|
| `bench/matrix/finetune/qa_corpus.py` (corpus R1) | question sans « (dossier actuel : {cwd})\n » ; `cwd` vide dans les blocs (`[1] ? $ …`) |
| banc v3 (`input` des cas qa) | 2 messages : `[système, "Historique…\n{ctx}\n\nQuestion : {q}"]`, sans accusé ni dossier |
| `context_start` | la production coupe au fil de l'eau ; un calcul d'un bloc donne un autre découpage (0052, 0053 : 4 omises au lieu de 3) |

## Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| Froid, 17 questions : p90 12,8 s sur l'i5 | VÉRIFIÉ | `p20-summary.json`, `before-cold` | une seule passe |
| Préchauffé : p90 0,36 s | VÉRIFIÉ | idem, `before-warm` | fenêtres multiples sur un même serveur non mesurées |
| Premier son à froid 12,8 s -> 0,01 s | EXÉCUTÉ | `after-cold`, 90 phrases dites | son réel non capté : Piper ajoute sa synthèse, cache P19 non mesuré ici |
| Texte et qualité inchangés | VÉRIFIÉ | 0 fuite sur 540 réponses ; `test_wait_phrase_never_reaches_the_window_nor_the_exchange_history` échouerait si la phrase fuyait | qualité bruitée (±3 points), aucun test statistique |
| Préchauffage interrompu repris | VÉRIFIÉ | `test_stream_background_cut_before_done_raises_so_the_warm_resumes`, `test_interrupted_warm_does_not_count_as_warm` | effet sur la latence en session réelle non isolé |
| Plafond serré perd des réponses | EXÉCUTÉ | 10 évaluations touchées, 3 passes Mac | n très petit |
