# G3c : suivi de reprise

Piste 4 : données publiques en bac à sable x2 à x3, étiquettes par un enseignant 27B ou plus, réaffinage de Gemma 4 E2B recette G3b, décision T5 contre G3b au test caché aligné L5 (G3b : qualité 64,0, note de production 68,8, inventions 17,6 %, questions 88,5).

| Étape | État | Détail |
|---|---|---|
| Données publiques | **fait** | 1 779 sorties (FR 883, EN 896), PII 0, contamination 0 contre v3 entier ; `data.md` |
| Étiquetage (enseignant 27B, juge) | **fait** | 1 633 gardées sur 1 753 (FR 809, EN 824) ; 122B-A10B essayé, pas nettement mieux, 27B gardé ; juge 9B 17,7 %, 27B 5,1 % sur 1 753, 6,8 % écartées ; `labels.md` |
| Mélange G3c | **fait** | RTX 3060 `/mnt/backup-hdd/stephbench-tmp/g3c/mix/` : train 5 445 (public 28 %), val 289 ; drop -2 publiques, scan 0 cas, PII 0 |
| Mélange G3c-t9 (mise à jour T9) | **fait** | RTX 3060 `g3c/mix-t9/` (`mix_g3c_t9.sh`) : mélange G5b (chaîne G3b sur `final-t9`, correctif de langue x2, corrections T9 x1) plus publiques G3c ; train **6 221** (public 24,5 %, corrections 842), val 283 ; scan 0 cas sur 6 504, audit_pii 0, prompts inconnus de `to_generic` 0 ; sha256 train `1b21fa68…`, val `b0ec456a…` |
| Réaffinage recette G3b | **fait** | 3060 : `s42` (ancien mélange, comparaison), `t9s42` (perte val 0,2463, adaptateur `1406a86a…`), `t9s7` (0,2514, `a53f9327…`), 778 pas chacun, rc=0 ; sorties `g3c/train/sft-<run>/`, journal `g3c/train/run.done` |
| GGUF f16, Q4_0, off-ple3 | prêt | `chain.sh` reproduit G3b tenseur pour tenseur (541/541 en f16, Q4_0 et off-ple3 ; seul `general.name` diffère, `gguf_cmp.py`) ; `finish.sh <graine>` (relais ssh depuis le Mac) enchaîne adaptateur, chaîne et copie vers la 3080 ; serveur Xeon `/root/steph-ft/g3c/chain.sh <nom> <adaptateur>` sous systemd-run (cœurs 0-31, 64G, nice 19) ; sorties `/root/steph-ft/g3c/ft/gguf/` |
| Contrôle DEV rapide | **fait** (2 graines) | `train.md` : qualité t9s42 64,5 et t9s7 65,0 contre 65,2 pour G3b, inventions 15,2 % et 12,6 % contre 15,1 %, aucun écart significatif ; entre graines, inventions -2,60 [-5,02 ; -0,19] : bruit d'entraînement du même ordre que l'effet ; GGUF `g3c-t9s{42,7}-*` sur serveur Xeon (off-ple3 t9s42 `14de8835…`, t9s7 `3e36aeed…`) |
| Banc v3 TEST une fois | **fait** : G3c non adopté, G3b reste (T5 non tenue, `eval.md`) | pré-enregistrement ci-dessous ; scripts `eval/` ; 3080 `/root/steph-ft/g3c/eval/`, serveur Xeon `/root/steph-ft/g3c/style/` |

## Pré-enregistrement du TEST (01 18:45, avant toute génération)

- **Candidat unique : `g3c-t9s7-off-ple3`** (`3e36aeed…`), choisi au DEV (qualité 65,0 contre 64,5 pour t9s42, inventions 12,6 % contre 15,2 %). t9s42 ne passe pas au TEST.
- Références de la même session : G3b off-ple3 (`eb6e7607…`), Gemma 4 E2B brut QAT q4_0 (`fa401b55…`), steph-speak v1.0 (`45414bd2…`, harnais affiné `705fdcb9`) ; Gemma sur le générique `8d90a662`.
- Règle T5 contre G3b off-ple3 : qualité non inférieure (IC qui n'est pas entièrement sous 0, lecture de R2, G3b et G5b), meilleur sur au moins un axe (IC au-dessus de 0 : qualité, note de production, inventions A7, questions, formulation 27B, langue), aucune régression significative (IC qui exclut 0 du mauvais côté) sur qualité, note de production, inventions, questions à réponse présente, mauvaise langue FR et EN, sortie FR sous prompt EN.
- Si le seul gain est aux inventions du 9B : contre-jugement 27B des évaluations discordantes (graine 7) avant de conclure.

Prochaine action (01 22:30) : G3c clos. **G3b off-ple3 reste** ; TEST : qualité +0,48 [-0,76 ; +1,67], inventions A7 -2,10 [-4,28 ; +0,04], formulation +2,5 [-6,7 ; +12,1], aucune régression (`eval.md`). Suite possible, décision de l'orchestratrice : contre-jugement 27B des inventions (hors pré-enregistrement, donc exploratoire), ou plusieurs graines d'entraînement avant tout nouveau TEST.

Ancienne Prochaine action (01 19:25) : TEST lancé. 3080 `/root/steph-ft/g3c/eval/eval-3080.sh` (12 runs, 2 couloirs, puis juge A7 ; journal `run.done` ; Ollama arrêté à 19:22, relancé par le script à sa sortie) ; GGUF vérifiés dans `/dev/shm/g3c-eval/` ; serveur Xeon `/root/steph-ft/g3c/style/style-xeon.sh g3c g3b` en attente du 27B de G5c (journal `style.done`) ; `eval/relay.sh` (depuis le Mac, flux seulement) relaie les runs graine 7. Ensuite : `g3c_eval.py` sur la 3080, `eval.md`.

Ancienne prochaine action (01 18:30) : mission SFT et DEV terminée. Décision à prendre par l'orchestratrice : test caché une fois contre G3b (aucun gain au DEV à confirmer), ou nouvelle itération (correctif de langue x3, dose publique réglée au DEV, plus de graines).

Ancienne prochaine action : SFT recette G3b sur `g3c/mix/train.jsonl` et `val.jsonl` (machine du corpus, 3060), `--generic-prompt`, graine 42 ; puis banc v3 dev, test une fois contre G3b.

- Ollama de la 3080 relancé (`active`) ; morceaux 27B supprimés de la 3080, 122B supprimé de serveur Xeon.
- RTX 3060 `/mnt/backup-hdd` à 98 % : `g3c/rootfs` (3,0 Go), `src`, `tpl` supprimables si la place manque (non supprimés).

## Contrôle sceptique (01 22:45)

| Point | Résultat |
|---|---|
| Chiffres du TEST | `eval/g3c-eval.json` (sha256 `b7cb338f…`) identique au fichier de la 3080 ; inventions recomptées sur `run.done` : G3c 377/2 478 = 15,21 %, G3b 429/2 478 = 17,31 % |
| Juge A7 | `run.done` : 6/6 FR et EN, passes A et B, avant (20:08) et après (21:20) |
| Fuite | empreintes v3 recalculées sur les 1 105 cas L01-L15 : publiques retenues 0 rejet, drop 0, Jaccard lignes max 0,333 ; mélange `mix-t9` sur RTX 3060 (6 504 exemples) 0 rejet, canari 0, shingles max 0,583 (seuil 0,6) |
| PII | `audit_pii.py` sur `public_g3c.retained.jsonl` et `review60.jsonl` : 0, liste de noms présente |
| Licences | 37 sources permissives (MIT, BSD, Apache-2.0, Zlib, CC0, Unlicense) ; licence de Pagila relue sur RTX 3060 : MIT |
| Corpus personnel | `mix-t9` seulement sur RTX 3060 ; la 3080 et serveur Xeon ne portent que des publiques et des runs du banc |
| GGUF | sha256 de `g3c-t9s7-off-ple3` et `g3b-off-ple3` identiques sur serveur Xeon et dans `/dev/shm/g3c-eval/` |
| Ollama de la 3080 | relancé par G3c à 21:20:12, **rearrêté à 21:20:39 par G5d**, dont le SFT tient la carte ; non relancé pour ne pas le gêner |
| Disques | 3080 `/` à 97 % (2,1 Go libres), RTX 3060 97 %, serveur Xeon 93 % ; `/dev/shm/g3c*` 14 Go sur la 3080, doublons supprimables, non supprimés |
