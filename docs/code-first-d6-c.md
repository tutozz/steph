# D6 lot C : paquets, git, conteneurs, infra dits en code

Suite de `docs/code-first-d6.md`, section 4, lot C. Branche `d6/C`.
Règles écrites d'après les formats documentés des outils ; cas et sorties du split **dev** lus pour vérifier, aucune réponse de modèle lue, split test jamais ouvert.
Entrée du modèle inchangée : tout passe par `resolve()` (code seul) ou `skeleton()` (gabarit du mode hybride, non branché).

## 1. Ce qui est dit en code

Code seul quand la phrase est complète : liste ou compteur entier, ou message connu traduit. Sinon gabarit, et le modèle garde la cause.

| Famille | Règle | Mode | Provenance (format) | Exemple dev |
|---|---|---|---|---|
| npm, pnpm | `added/removed/changed N packages`, vulnérabilités par gravité, paquets dépréciés | code si chaque ligne est une ligne de bilan, sinon gabarit | npm 10 `reify-output`, pnpm 9 et 10 | `v3-js-node-0003`, `0010`, `0025` |
| npm | `npm audit` : total, gravités, paquets tirés des chemins `node_modules/` | code ; noms seulement si leur nombre égale le total de npm | rapport texte de `npm audit` | `v3-js-node-0011`, `0035` |
| npm | `EBADENGINE`, `E404` et `ERR_PNPM_FETCH_404`, `npm ci` désynchronisé | code | messages d'erreur npm et pnpm | `v3-js-node-0013`, `0019`, `0026` |
| npm, pnpm, pip, brew | `outdated` : compte, puis « nom vers dernière version » | code | tableaux `npm outdated`, `pnpm outdated`, `pip list -o`, `brew outdated` | `v3-js-node-0033`, `v3-python-0003`, `v3-packages-system-0022` |
| pip | `-r fichier` : paquets demandés par le fichier ; `Cannot install a==x and b==y` | code | lignes `Collecting X (from -r …)`, ResolutionImpossible | `v3-python-0002`, `0014` |
| pip | échec de construction d'une roue | gabarit | `Failed to build 'X'`, `Failed building wheel for X` | `v3-python-0015`, `0016`, `0034` |
| uv, poetry | `Installed N packages`, `+ nom==version`, `Audited`, `uv pip compile` ; `Package operations`, projet courant | code si chaque ligne est documentée | sorties uv et poetry | `v3-python-0009`, `0023`, `0025` |
| apt, dpkg | `apt list --upgradable`, `apt-cache search`, `apt-cache policy`, `dpkg -l` (lignes `ii`) | code ; toute ligne hors format ou un tube font taire | apt 2.x, gettext français à espace insécable, dpkg-query | `v3-packages-system-0008`, `0065`, `0066`, `0087` |
| brew | `brew uses` compté ; `brew doctor` compté | code ; gabarit pour doctor | sorties Homebrew | `v3-packages-system-0026`, `0027` |
| git | `branch` (locales, courante, distantes, amont disparu, en avance, en retard) | code | ref-filter, anglais et français | `v3-vcs-git-0029`, `0031` |
| git | push sans amont, avance rapide impossible, hôte introuvable, HEAD détachée, rebase en cours, `log --stat` | code | builtin/push.c, merge.c, wt-status.c, ssh et libcurl | `v3-vcs-git-0015`, `0020`, `0024`, `0039`, `0040`, `0043`, `0046` |
| gh | non connecté | code | message de GitHub CLI | `v3-infra-0014` |
| docker | BuildKit : instruction inconnue, image de base introuvable, fichier absent du contexte | code ; autre `failed to solve` en gabarit | BuildKit | `v3-containers-0011`, `0012` |
| kubectl, helm | serveur injoignable (délai, refus, hôte) ; `helm template` (chart, release, manifestes) ; `helm lint` en échec | code ; lint en gabarit | client-go, helm | `v3-containers-0015`, `0023`, `0024` |
| terraform | init, apply avec sorties, plan par action, `No changes.`, `state list` ; erreur ou avertissement en gabarit | code | Terraform 1.x, OpenTofu | `v3-infra-0001` à `0005` |

## 2. Mesure hors ligne, split dev

`score_production.py` rejoué sur les sorties existantes ; avant : master `137eb9a`, après : `d6/C`. Harnais affiné L5 (`8c686025`) pour v1.0, générique L5 (`e96d54d4`) pour Gemma.

| Modèle | Avant (g. 7 / 42 / 123) | Après | Moyenne | Évaluations changées | Mieux / moins bien (par graine) |
|---|---|---|---:|---:|---|
| v1.0 | 58,53 / 58,07 / 57,73 | 63,41 / 62,70 / 62,54 | 58,11 -> **62,88** (+4,77) | 80 | 61, 60, 61 / 0 |
| Gemma brut L5 (substitut de G3b) | 68,88 / 68,76 / 68,93 | 71,75 / 71,83 / 71,71 | 68,86 -> **71,76** (+2,91) | 80 | 49, 52, 50 / 3, 2, 4 |
| G3b | - | - | non mesuré | - | passe dev de la 3080 toujours en attente de 4 Go libres |

| Indicateur | Valeur |
|---|---|
| Part dite en code | 40,8 -> **49,7 %** (+74 évaluations) |
| Gabarits (mode hybride) | 10 évaluations ; estimé par concaténation : v1.0 +0,06, Gemma +0,23 |
| Baisses chez Gemma | `v3-packages-system-0067` (dpkg : trois premiers noms, pas le paquet attendu), `v3-infra-0004@en` (plan sans la valeur changée), `v3-vcs-git-0020@en` (phrase d'hôte introuvable existante) |

## 3. Relecture

| Contrôle | Résultat |
|---|---|
| Phrases de code changées sur dev | 80 (40 cas, FR et EN), **toutes relues** contre la sortie brute |
| Phrase fausse trouvée | 1, corrigée : `npm audit` disait « 9 paquets concernés » pour 11 ; un bloc sans ligne `Severity:` était omis. Noms tirés des chemins `node_modules/`, et dits seulement si leur nombre égale le total de npm |
| Compteurs recomptés à part | helm 4 manifestes, brew 82 et 188, apt 87 et 395, git 6 commits, npm 11 et 5 paquets |
| Corpus publics (`bench/fixtures.json`, `benchmark/tools/cases`) | 346 phrases, 4 changées, toutes vraies (npm install du Speak Bench, conflit pip) |
| Pièges posés en test | tube, avertissement inconnu, script postinstall, version candidate plus ancienne (épinglage), plage de moteur complexe, option inconnue avant le chart, lignes uv indentées, `npm audit fix` |

## 4. Limites

| Limite | Effet |
|---|---|
| Mesure dans l'échantillon : phrases relues contre les faits dev | le test, lu une fois à l'intégration, donnera moins (D5 : environ 25 % de moins) |
| Tournure d'`apt-cache policy` choisie après lecture des faits dev (« libc6 peut être mis à jour » plutôt que « Mise à jour disponible : libc6 ») | aussi plus naturelle à l'oral, mais le gain de cette ligne est optimiste |
| G3b absent du dev | gains Gemma à confirmer sur `g3b-dev-b7.json` |
| `skeleton()` n'est branché nulle part | le mode hybride (réglage `code_skeleton`) reste à écrire dans `narrator` |
| `dpkg -l` dans un terminal étroit tronque les noms | le nom dit est celui affiché, tronqué |
| Jamais entendu en synthèse vocale | versions (`2.41-12+deb13u4`), `@scope/nom`, sujets de commit avec deux-points |
