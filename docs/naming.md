# Nommage : table de référence

Table unique de nommage, tâche N1 du journal de mission interne (non publié). Consolide les décisions
déjà prises dans `docs/open-source.md` (section « Décisions prises », D-nommage et
section 2.2) et une note interne (non publiée) (section 5), et sert de référence au garde-fou
`tests/test_naming.py`.

## Noms actifs

| Nom | Usage | Forme affichée | Forme technique | Version |
|---|---|---|---|---|
| steph | produit | `steph` (toujours minuscules, jamais seul dans un titre ou une carte : toujours accolé à un descripteur) | `steph` | v1 |
| steph-speak | famille de modèles affinés | `steph-speak` | `steph-speak` | v1 |
| Steph Speak Bench | benchmark | **Steph Speak Bench** (casse de titre, décision D-nommage explicitement maintenue malgré la proposition alternative de une note interne (non publiée) section 5.1) | `steph-speak-bench` | v1 |
| steph-speak-train | jeu d'entraînement | `steph-speak-train` | `lsmdx/steph-speak-train` | v1 |
| LSMDX | éditeur | `LSMDX` | `lsmdx` | - |
| Modèle GGUF publié | fichier livré | `steph-speak-fr-<base>-<taille>-<méthode>-v<maj>.<min>-<quant>.gguf` | idem (schéma `docs/open-source.md` section 2.2) | v1, **nom réel à revérifier après R1** (base finale Granite ou Qwen pas encore tranchée) |
| Canari anti-contamination | `benchmark/data/v1/` | `termspeak-canary-v1-5e0c83a1d7f2` (conservé tel quel) | idem | v1, gelé (voir « Exclu du périmètre ») |

## Anciens noms retirés des surfaces publiques (cette tâche, N1)

| Ancien nom | Remplacé par | Surfaces corrigées |
|---|---|---|
| TermSpeak (chaîne visible, hors canari) | Steph Speak Bench | `CHANGELOG.md` (déjà fait avant N1, vérifié) |
| Codes de tâche internes (P15, P16, P17, K3, R1, A5b, A9, A10, H3, H3a, I1, I2, O1, O2, O3, D3, L2, L2a) dans un texte public | description en langage clair (« le réentraînement final », « l'extension anglaise », etc.) ou suppression pure | `README.md`, `README.fr.md`, `CHANGELOG.md`, `benchmark/README.md`, `benchmark/README.fr.md`, `benchmark/tools/score_resolve.py`, `benchmark/tools/cases/real.py`, `docs/model-card-draft.md`, `docs/dataset-card-draft.md`, `docs/readme-charts/build.py`, `docs/readme-charts/build_readme.py`, `site/public/index.html`, `site/public/en/index.html`, `site/public/modele/index.html`, `site/public/en/model/index.html` |
| « Candidat P17 » / « Candidate P17 » (jargon interne utilisé comme nom du modèle) | `steph-speak` | `site/public/index.html`, `site/public/en/index.html`, `site/public/modele/index.html`, `site/public/en/model/index.html` |
| `llm/steph-universal` | conservé : identifiant interne du catalogue, jamais affiché (voir « Exclu du périmètre ») | `src/steph/data/catalog.json` (non modifié, décision documentée) |

Images régénérées après ces corrections : `assets/charts/{hero,quality,speed,size}.{en,fr}.{light,dark}.png`
et `assets/readme/hardware.{en,fr}.{light,dark}.png`, via `docs/readme-charts/build.py` et
`docs/readme-charts/build_readme.py`. Aucun chiffre n'a changé, seul le texte des légendes.

## Exclu du périmètre (et pourquoi)

| Surface | Raison |
|---|---|
| `docs/mission-*.md`, `bench/matrix/`, `benchmark/results/*.json`, `benchmark/data/v1/` | suivi interne ou données figées, exclusion explicite de la consigne N1 |
| Canari `termspeak-canary-v1-5e0c83a1d7f2` | `data/v1` est gelé (`docs/open-source.md`, décision O2) ; le renommer romprait des sommes de contrôle déjà publiées dans `benchmark/results/*.json` |
| `docs/readme-charts/data.json`, `docs/readme-charts/sources.md` | ledger de provenance interne des chiffres du README, jamais lu par le pipeline de rendu ni affiché à un lecteur ; même nature que le journal de mission interne (non publié) |
| Commentaires de code (`src/steph/config.py`, `digest.py`, `narrator.py`, `prompts.py`, `server.py`, `tts.py`) | notes d'ingénierie internes, jamais affichées ni publiées ; renommage massif d'identifiants internes non fait sans nécessité (consigne N1) |
| Labels `sys.modules` internes (`termspeak_run`, `termspeak_validate`...) de `benchmark/tools/build_dataset.py`, `score_resolve.py`, et des `tests/` qui les chargent | purs identifiants de chargement dynamique de module, jamais affichés ; candidats à un nettoyage futur, signalés ci-dessous |
| Champs `_doc` et `quality_note` de `src/steph/data/catalog.json` | jamais lus par le code (`src/steph/setup.py` n'affiche que `label`, vérifié par `tests/test_naming.py::test_catalog_labels_have_no_old_name`) |
| Liens `github.com/tutozz/steph` (README, CITATION, croissant.json, pyproject.toml, packaging Homebrew) | décision d'espace de noms GitHub non tranchée : le compte `lsmdx` existe déjà côté tiers (`docs/open-source.md`, « Collisions de noms »), décision utilisateur attendue avant O3 |
| Descripteurs « talking terminal » / « terminal parlant » face à « speaking terminal » / « terminal qui parle » | incohérence de wording relevée par une note interne (non publiée) (écarts 1-2), assignée à la tâche M2 (réécriture de la landing et du README), pas un ancien nom au sens de N1 |
| Alias CLI proposés (`steph doctor`, `steph ctl silence`) | décision non tranchée (une note interne (non publiée), section « Décisions à prendre ») ; ajouter un alias est une fonctionnalité, pas une correction de nommage |
| `*.md` (copy-landing, copy-readme, strategy, research-*) | brouillons de la tâche M2, pas encore appliqués ; contiennent encore `granite-soup`, des codes de tâche et « candidat(s) » en attendant cette réécriture |

## À revérifier après R1

| Élément | Pourquoi |
|---|---|
| Nom réel du fichier GGUF (`steph-speak-fr-<base>-...-v1-<quant>.gguf`) | la base finale (Granite 4.0 H 350M ou Qwen3.5 0.8B) est tranchée à R1 |
| `src/steph/data/catalog.json` : `source`, `file`, `available` de `llm/steph-universal` | à activer (`available: true`) une fois le modèle publié |
| Valeurs « à remplir après le réentraînement final » dans `docs/model-card-draft.md` et `docs/dataset-card-draft.md` | R1 fournit les chiffres réels (scores, latence, empreinte carbone, tailles du corpus) |
| Table « Nom réel du GGUF » ci-dessus | à recopier dans cette table une fois le fichier nommé |

## Décision rappelée sur l'affichage du banc

une note interne (non publiée) (section 5.1) propose d'afficher `steph-speak-bench` partout
(identifiant seul, comme `SWE-bench`), plutôt que « Steph Speak Bench » en casse de titre.
Cette tâche (N1) applique la consigne reçue et **garde la casse de titre « Steph Speak
Bench »** pour l'affichage : c'est la décision D-nommage de `docs/open-source.md`, non
révisée. Si l'utilisateur valide la proposition de `naming.md` plus tard, c'est un
changement d'affichage à refaire sur les mêmes surfaces que celles listées ci-dessus.
