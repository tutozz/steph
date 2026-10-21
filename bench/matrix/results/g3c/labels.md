# G3c, étiquettes : sorties publiques étiquetées au 27B, mélange G3c

Piste 4, étape étiquettes. **Rien n'est entraîné** ; le mélange est prêt pour le réaffinage recette G3b.

**Résultat : 1 633 étiquettes gardées sur 1 753** (FR 809, EN 824), enseignant Qwen3.5 27B, juge A7 9B puis 27B.
Mélange G3c : **train 5 445, val 289**, dont 1 527 et 104 lignes publiques ; contamination 0 contre le banc v3 entier, PII 0.

## Enseignant : 27B gardé, 122B écarté

Candidat plus gros : **Qwen3.5 122B-A10B UD-Q3_K_XL** (unsloth, 57 Go, MoE à 10B actifs), seul modèle plus fort que le 27B qui tient sous 64 Go sur serveur Xeon. Même échantillon de 60 sorties publiques (30 FR, 30 EN, toutes les familles), mêmes messages de production, même requête (`label.query`). Relecture à la main des 120 étiquettes : `review60.jsonl`.

| Mesure, 60 étiquettes relues | 27B Q4_K_M (`84b5f7f1`) | 122B-A10B UD-Q3_K_XL |
|---|---|---|
| Invention nette | **0** | **0** |
| Statut contredit (fait vrai dans la sortie, code 0 affiché) | 1 (psql) | 2 (psql, make) |
| Défaut d'oral | 5 : hash de 40 caractères lu 2 fois, échecs non annoncés, PID au lieu des processus, éléments non nommés | 3 : phrase sans syntaxe, « mot de passe visible », « serveur absent » déduit |
| Plus informatif que l'autre | 3 | 8 (nombres, ports, total d'erreurs) |
| Langue de la réponse | 60/60 dans la langue du prompt | 60/60 |
| Vitesse | 3080 partielle, 2 slots : 4,3 s par étiquette | serveur Xeon CPU, 1 slot : 9,7 s par étiquette |

**Décision : 27B.** Aucune différence d'invention mesurable sur 60 (0 contre 0) ; le 122B écrit un peu mieux, pas « nettement ». Le 122B a été supprimé de serveur Xeon (disque à 96 %).

Pour le corpus personnel existant (`final-x4-l5`, étiqueté au 27B en X4) : **rien ne justifie un réétiquetage au 122B**. La comparaison porte sur des sorties publiques, pas sur le corpus : le corpus ne quitte pas sa machine et n'a pas été relu ici.

## Étiquetage

| Élément | Valeur |
|---|---|
| Code | `bench/matrix/finetune/g3c_label.py` (10 tests verts) |
| Entrée de l'enseignant | `label.build_messages(rec, 587, lang)` : prompt de production générique (`SUMMARY_SYSTEM`, `SUMMARY_SYSTEM_EN`), digest ou sortie compacte à 587 caractères, **bloc de faits L5** (561 tâches sur 1 758 le reçoivent) |
| Ligne d'entraînement | `TRAIN_SYSTEM` de la langue, message utilisateur de production, étiquette ; `train_sft_gemma.py --generic-prompt` le remplace par le prompt générique, comme pour G3b |
| Tâches | 1 758 (1 779 sorties moins 21 entrées identiques) ; FR 874, EN 884 ; 524 seraient dites en code par `resolve()` en production |
| Enseignant | Qwen3.5 27B Q4_K_M `84b5f7f112156d63`, 3080, 32 couches sur la carte, 2 slots, température 0, pénalité de présence 1, 64 jetons, `--cache-ram 0` ; le GGUF tenait ni sur le disque ni dans `/dev/shm` de la 3080 : deux morceaux `gguf-split`, reconstruits par plages d'octets HF et vérifiés au sha256 contre le découpage fait sur serveur Xeon |
| Consigne de langue | aucune : 60/60 dans la langue du prompt sur l'échantillon ; le contrôle de langue n'a retiré aucune étiquette |
| Écartées avant juge | 5 vides ou trop longues |
| Juge 1 | A7 intact, Qwen3.5 9B `03b74727`, 2 passes ; contrôles **6/6 FR et EN, A et B, avant et après** |
| Juge 2 | même A7, Qwen3.5 27B, 2 passes, sur les 475 étiquettes que le 9B signale (invention ou douteux) ; contrôles 6/6 FR et EN avant et après |
| Règle | gardée si le 9B dit ok, ou si le 27B dit ok sur une signalée ; sinon écartée (invention et douteux du 27B) |
| Validation | 5 % des lignes, par hash du message utilisateur |

## Taux d'invention mesurés

| Mesure | Valeur |
|---|---|
| Juge 9B, 2 passes, sur 1 753 | invention **17,7 %** (311), douteux 9,4 % (164), ok 72,9 % |
| Juge 27B sur les 475 signalées | ok 355, douteux 30, invention **90** |
| Invention au 27B rapportée à 1 753 | **5,1 %** (90) ; borne basse : les 1 278 « ok » du 9B n'ont pas été rejugées au 27B |
| Écartées au total | **6,8 %** (120) ; FR 6,9 %, EN 6,8 % |
| Relecture à la main, 60 étiquettes 27B | 0 invention nette, 1 statut contredit (1,7 %) |
| Juge 9B sur ces 60 | 10 signalées (3 invention, 7 douteux), **10 fausses** à la relecture ; le 27B en blanchit 9 |
| Rappel R2-C4 (enseignant et juge 9B) | 13,9 % comparable, 11,9 % en fin de chaîne |

Catégories des 90 inventions 27B : ligne 37, nombre 31, statut 16, cause 14, nom 12.

| Famille | Jugées | Gardées | Écartées |
|---|---:|---:|---:|
| files | 303 | 288 | 5,0 % |
| tests | 302 | 277 | 8,3 % |
| lint-format | 269 | 251 | 6,7 % |
| bases | 155 | 150 | 3,2 % |
| packages-system | 141 | 130 | 7,8 % |
| **build-native** | 137 | 107 | **21,9 %** |
| docker | 86 | 84 | 2,3 % |
| vcs-git | 77 | 73 | 5,2 % |
| typage | 60 | 60 | 0 % |
| services-logs | 60 | 55 | 8,3 % |
| network-transfer | 46 | 45 | 2,2 % |
| shell-scripts | 35 | 35 | 0 % |
| python | 32 | 28 | 12,5 % |
| network, rust-go, js-node, processes | 50 | 50 | 0 % |

## Mélange G3c

Sur l'hôte de la 3060 (machine du corpus), `mix_g3c.sh` : mélange G3b inchangé (`work/mix`, sha256 `b53e0c42…` : `final-x4-l5` chaîne R3-T3 plus correctif de langue x 2) plus les étiquettes publiques gardées. Chaque fichier passe par `leak_check.py drop` contre les empreintes v3 au HEAD (1 105 cas), puis `scan` du mélange.

| Source | Train | Part | Val |
|---|---:|---:|---:|
| `fr_summary` (corpus) | 1 930 | 35,4 % | 102 |
| `en_summary` (corpus, x2) | 894 | 16,4 % | 22 |
| **g3c_public_en** | **777** | **14,3 %** | 46 |
| **g3c_public_fr** | **750** | **13,8 %** | 58 |
| `detail` | 292 | 5,4 % | 32 |
| `start` | 272 | 5,0 % | 14 |
| `langfix_en_fr` (correctif G3b, x2) | 250 | 4,6 % | 0 |
| `qa` | 152 | 2,8 % | 7 |
| `progress`, `flux`, `summary_residual` | 128 | 2,4 % | 8 |
| **Total** | **5 445** | | **289** |

- Public : **28,0 %** du train. Résumés : corpus 2 824, public 1 527.
- `leak_check drop` : G3b train 0 sur 3 918, val 0 sur 185 ; public train **2 retirées** sur 1 529 (cas `v3-rust-go-0001`, vu par le bloc L5 et pas par le contrôle de l'étape données), val 0.
- `scan` du mélange : 5 734 exemples, **0 cas rejeté**, 0 ligne canari, Jaccard lignes max 0,455, shingles max 0,583.
- `audit_pii.py` sur les lignes publiques gardées : **0**.

## Emplacements

| Quoi | Où |
|---|---|
| Mélange G3c | RTX 3060 `/mnt/backup-hdd/stephbench-tmp/g3c/mix/train.jsonl` (sha256 `f239b37c19d2…`), `val.jsonl` (`c0146a56e91d…`), `counts.json`, `leak.log`, `SHA256SUMS` |
| Étiquettes publiques gardées | RTX 3060 `/mnt/backup-hdd/stephbench-tmp/g3c/labels/public_{train,val}.jsonl` (`e206b5886…`, `33c310adc…`) ; aussi 3080 `/root/steph-ft/g3c/work/` |
| Étiquettes brutes, verdicts 9B et 27B, journaux | 3080 `/root/steph-ft/g3c/work/` (`labels-27b.jsonl`, `judge9/`, `judge27/`), `/root/steph-ft/g3c/*.done` |
| Échantillon 122B | serveur Xeon `/root/steph-ft/g3c/work/labels-122b.jsonl` |
| Relecture | `review60.jsonl` (dépôt) |

Pour entraîner : `train_sft_gemma.py --train .../g3c/mix/train.jsonl --val .../g3c/mix/val.jsonl --generic-prompt`, recette G3b (graine 42, lr 1e-4, 2 époques, lot 16, micro 4, maxlen 2 048).

## Doutes

- **Une seule relecture humaine de 60**, par l'agent : pas une relecture de l'utilisateur.
- Les 1 278 étiquettes « ok » du 9B **n'ont pas été rejugées au 27B** : le 9B rate des inventions que le 27B verrait.
- **build-native** perd 21,9 % : make et configure restent la famille la plus dure pour l'enseignant.
- Le statut affiché « succès (code 0) » contredit parfois une erreur réelle (psql, `| head`) ; l'enseignant dit « Échec », le juge laisse passer. Ce que Gemma doit dire là n'est pas tranché.
- 28 % du train est public : la dose n'a pas été réglée. Un essai à dose réduite sur DEV dirait si le corpus réel est dilué.
- Enseignant sur la 3080 (couches en partie sur la carte), juge 27B aussi ; le 27B de X4 tournait en CPU : mêmes poids, calcul différent.
- Comparaison 27B contre 122B : le 122B est en Q3, le 27B en Q4 ; 60 cas ne distinguent pas deux taux faibles.

## Preuves

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| Lignes au format d'entraînement L5 | VÉRIFIÉ | `test_g3c_label.py` : échouerait si l'entrée différait de `label.build_messages` ou si le système n'était pas `TRAIN_SYSTEM` | rendu `--generic-prompt` non rejoué sur ces lignes |
| Règle de garde 9B puis 27B | VÉRIFIÉ | test `final_verdict` ; `keep` : ok9 1 278, ok27 355, rejet 120 | - |
| Juges valides | VÉRIFIÉ | contrôles 6/6 FR et EN, A et B, avant et après, 9B et 27B | contrôles plantés, pas de mesure de rappel sur ces données |
| 27B et 122B sans invention nette sur 60 | EXÉCUTÉ | `review60.jsonl`, relecture de l'agent | aucune relecture humaine ; 60 cas |
| Mélange sans fuite | VÉRIFIÉ | `scan` : 0 cas rejeté sur 5 734 ; `drop` en a retiré 2 | seuils v3-fp1, pas de contrôle sémantique |
| PII 0 | VÉRIFIÉ | `audit_pii.py` : 0 sur train et val publics | liste de noms du Mac seulement |
| Effet sur Gemma | JAMAIS EXÉCUTÉ | - | aucun entraînement, aucun banc |
