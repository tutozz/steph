# L5 : bloc de faits extraits en code dans l'entrée du modèle

Levier L5 de `docs/deterministic-aids.md`. Il **change l'entrée du modèle** : il reste derrière `facts_block = false`, défaut de `Config`.
Mesure sur le split **dev** seulement, 3 graines. Aucune réponse du split test n'a été lue ni générée.

## Verdict

| Question | Réponse | Preuve |
|---|---|---|
| Gemma 4 E2B brut, sans réentraînement | **+1,5 pt** de note composite (59,3 -> 60,8), IC 95 % [0,4 ; 2,7], signe p = 0,011 | `bench/matrix/results/aids-input/l5-dev.json` |
| Gemma, lignes qui reçoivent un bloc | **+7,1 pts** (51,3 -> 58,4), IC [2,1 ; 12,1] | idem, `gemma-diff-facts-rows` |
| v1.0, jamais entraîné sur ce format | -0,6 pt (52,1 -> 51,5), IC [-1,7 ; 0,5] : pas de gain, recul non établi | idem, `r1-diff` |
| Interdits touchés (indicateur d'invention, pas le juge) | Gemma 3,8 % -> 3,6 % ; v1.0 3,6 % -> 4,2 % | colonne `forbidden_pct` |
| Juge A7 | **non lancé** : la 3080 sert à G3, l'A1000 ne tient pas le 9B | - |
| Entrer dans le prochain affinage ? | **G3 suivant : oui**, en variante mesurée contre le format actuel. **G5 : oui, en A/B** d'entraînement | section « Conclusion » |

## Ce qui est codé

| Fichier | Contenu |
|---|---|
| `src/steph/digest.py` | `extract_facts(cmd, exit_code, output, language)` : 5 faits au plus, 200 caractères chacun |
| `src/steph/prompts.py` | `facts_block()` ; `summary_messages` et `finetuned_summary_messages` prennent `facts=None` ; sans fait, entrée identique à l'octet |
| `src/steph/config.py` | `facts_block: bool = False` |
| `src/steph/narrator.py` | `_finish` passe les faits seulement si `cfg.facts_block` |
| `src/steph/strings.py` | libellés `facts.*` FR et EN |
| `bench/matrix/v3/tools/facts_harness.py` | harnais variante : reconstruit chaque résumé sans faits, refuse s'il diffère du harnais de base, puis ajoute le bloc |
| `bench/matrix/results/aids-input/analyze_l5.py` | note composite (`score_production.score_run`), écart apparié par cas (`power_v3.compare`), interdits touchés |

Forme du bloc, placé entre la durée et la sortie ; le prompt système ne change pas :

```
Commande : make -j8
Statut : succès (code 0)
Durée : 12.0 s ; 380 lignes affichées
Faits extraits en code :
- Avertissements dans : utimens.c
- Projet : patch-2.7.6
Sortie :
...
```

## Règles et origine

Chaque fait est une ligne recopiée de la sortie ou un nom lu dans un format fixe. Seul compte fait en code : les lignes `config.status: creating`, une par fichier.

| Fait | Condition | Source du format | Exemple qui l'a inspiré |
|---|---|---|---|
| Erreur principale | code non nul ; `configure: error:` (dernière, hors `in '…'`), puis `fichier:ligne:col: error:` (GCC, Clang, TS), `error[E…]` + `-->` (rustc), traceback Python (dernier cadre et exception), sinon dernière ligne `error:`, `fatal:`, `E:`, `npm error` | manuels GCC, autoconf, rustc, Python, npm | dev `v3-build-native-0059`, `v3-vcs-git-0015` |
| Erreur de script | `<script>: line N: msg` ou `ligne N : msg`, même en code 0 | format d'erreur de bash | dev `v3-shell-scripts-0021`, `0053` |
| Premier test en échec | code non nul ; `FAILED x::nom` (pytest), `FAIL: nom (` (unittest), `---- nom stdout` (cargo), `--- FAIL:` (go), `not ok N -` (TAP), `●` (Jest) | formats publics de ces lanceurs | dev `v3-tests-0090`, `0102` |
| Avertissements | fichiers distincts des lignes `fichier:ligne:col: warning:`, 3 au plus, **jamais comptés** | format GCC | dev `v3-build-native-0042`, `0047` |
| Fichiers générés | configure réussi : Makefile et config.h s'ils sont créés, et le nombre de lignes `creating` | sortie de `config.status` | dev `v3-build-native-0056`, `0061` |
| Projet | plus court `Entering directory` / `on entre dans le répertoire` de make | messages de GNU make, anglais et français | dev `v3-build-native-0070`, `0073` |
| Bilan de l'outil | 2 dernières lignes de bilan connues (pytest, unittest, Jest, Vitest, cargo, deno, node --test, ruff, tsc, eslint, clang, pylint, npm, pnpm, pip, uv, poetry, terraform, rsync, wget, apt, `sha*sum -c`, wc, cmake, gradle, git) ; ou dernière ligne avec un nombre isolé et un mot de bilan, hors visualiseurs, listes et tubes | formats publics de ces outils | dev `v3-lint-format-0035`, `v3-shell-scripts-0005`, `v3-infra-0002` |

Exclusions posées en relisant les faits extraits sur dev, **avant tout passage de modèle** :

- une ligne `ERROR: failed to solve` (docker) n'est pas un test : `FAIL: nom (` exigé ;
- un renvoi vers un journal (`A complete log of this run…`, `See config.log`) n'est jamais l'erreur ;
- une ligne de données n'est pas un bilan : position `13:14`, horodatage de journal, `***` de make, ligne d'erreur ou d'avertissement, nom de fichier avec des chiffres ;
- apostrophes gardées (`pas d'alternatives`), contrairement à `_clean` de `resolve()`.

Couverture sur dev (harnais générique, lignes envoyées au modèle) :

| Mesure | Valeur |
|---|---:|
| Évaluations envoyées au modèle | 452 |
| dont avec un bloc | 184 (41 %), 92 cas |
| Faits exigés sur ces lignes | 398 |
| dont présents dans le bloc | 212 (53 %) |
| Blocs qui touchent un interdit du banc | **0** |

## Mesure

| Élément | Valeur |
|---|---|
| Machine | A1000 (portable A1000), llama.cpp Vulkan, `bench_run.py` au HEAD (`--cache-ram 0`), deux couloirs parallèles, une seule session |
| Modèles | Gemma 4 E2B QAT q4_0 (`loop/x3/raw`), v1.0 `r1-v1.0-Q4_K_M` (`loop/x1judge`) |
| Harnais | générique `dev.generic.json` `247b1141`, variante `e96d54d4` ; affiné `harness/dev.json` `1b8f7402`, variante `8c686025` |
| Graines | 7, 42, 123 ; base Gemma 7 et 42 reprises de G3 (même serveur, même `bench_run.py`, même harnais) |
| Note | `score_production.py` : ce que steph dit vraiment, ancrage actif, code avant le modèle |
| Bruit | sur les lignes sans bloc, 0 cas discordant entre base et variante, pour les deux modèles : à entrée égale, la génération est identique ; tout écart vient du bloc |

| Modèle | Variante | Graine 7 | Graine 42 | Graine 123 | Moyenne | Lignes du modèle | Lignes avec bloc | FR | EN | Interdits touchés |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemma 4 E2B | base | 58,8 | 59,5 | 59,6 | 59,3 | 56,5 | 51,3 | 59,0 | 59,6 | 3,8 % |
| Gemma 4 E2B | **faits** | 60,6 | 61,2 | 60,7 | **60,8** | 58,9 | **58,4** | 61,1 | 60,5 | 3,6 % |
| v1.0 | base | 52,5 | 52,2 | 51,7 | 52,1 | 45,1 | 43,7 | 51,2 | 53,1 | 3,6 % |
| v1.0 | faits | 51,5 | 51,8 | 51,3 | 51,5 | 44,1 | 40,7 | 50,8 | 52,2 | 4,2 % |

Écart apparié par cas (moyenne des graines puis des langues, bootstrap 10 000 tirages) :

| Modèle | Portée | Écart | IC 95 % | MDE | Cas discordants | Signe p |
|---|---|---:|---|---:|---:|---:|
| Gemma | dev entier (429 cas) | **+1,52** | [0,44 ; 2,67] | 1,58 | 63 | 0,011 |
| Gemma | cas avec bloc (92) | **+7,07** | [2,05 ; 12,05] | 5,05 | 63 | 0,011 |
| v1.0 | dev entier | -0,63 | [-1,69 ; 0,46] | 1,54 | 58 | 0,90 |
| v1.0 | cas avec bloc | -2,93 | [-7,92 ; 2,14] | 5,07 | 58 | 0,90 |

Par famille, écart moyen des 3 graines (points de note de famille) :

| Famille | Gemma | v1.0 |
|---|---:|---:|
| build-native | **+7,0** | **+7,1** |
| rust-go | +8,6 | -7,0 |
| js-node | +8,0 | -0,7 |
| lint-format | +4,9 | -0,9 |
| infra | +3,2 | -7,8 |
| shell-scripts | +1,1 | -6,3 |
| tests | -0,6 | -3,1 |
| vcs-git | -2,7 | -2,2 |
| data | -2,3 | 0,0 |

Ce que le bloc change chez Gemma (graine 7, lecture après coup, aucune règle modifiée ensuite) : `./configure` dit « Makefile, config.h générés » au lieu de « gawk non trouvé » ; `make` nomme le projet (`grep-3.11`, `gzip-1.12`) au lieu de « 6 sections lib » ; `npm audit` et `ruff` donnent le compte (« 11 vulnérabilités », « 5 corrigibles ») ; un script nomme la ligne en faute. Reculs : le modèle reprend parfois le bilan brut au lieu du fait clé (`cargo clippy` : « 59 sections » ; `pip install sklearn` perd la cause).

## Limites

| Limite | Effet |
|---|---|
| Règles écrites en lisant les sorties dev | gain optimiste ; le test tranchera, une fois, à la mesure finale |
| Juge A7 non lancé | inventions non jugées ; seul l'indicateur « interdit touché » est mesuré |
| v1.0 n'a jamais vu le format | son recul (non établi) ne dit rien d'un modèle entraîné avec le bloc |
| Résumés seulement | le détail (F10) et les questions (F7) n'ont pas de bloc |
| Une seule écriture du bloc testée | pas de consigne système ajoutée ; un modèle brut pourrait mieux s'en servir avec une ligne de consigne, non mesuré |

## Conclusion

- **G3 suivant (Gemma affiné)** : oui. Le bloc apporte +1,5 pt à Gemma brut sans rien lui apprendre, et +7,1 pts sur les cas où il existe. Construire le corpus avec `facts_block` actif (les entrées se régénèrent en code, sans réétiquetage) et mesurer l'affiné contre le même affiné sans bloc. Tout gain impose de livrer le modèle et le réglage ensemble.
- **G5 (petit modèle)** : oui, en A/B d'entraînement. v1.0 n'en tire rien sans l'avoir appris (-0,6, non établi) ; un 350M ne sait pas encore s'en servir, mais le fait clé en tête est ce qui lui manque le plus (443 faits manqués sur 509 étaient déjà dans son entrée).
- **Ordre** : après L1 à L3, qui rapportent +4,6 à +6,5 pts sans réentraînement. L5 ne rapporte que sur un modèle qui le lit, donc au prochain affinage.
- **Défaut** : `facts_block` reste faux tant qu'aucun modèle livré n'a été entraîné avec.
