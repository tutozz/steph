# Banc v3 - conception

Banc d'évaluation de steph-speak, versionné, assez grand pour départager deux modèles proches.
Le banc de 36 cas (`facts.v2.json`) et le Steph Speak Bench public (`benchmark/`) restent intacts.

## 1. Pourquoi

| Constat (T5, tour 1) | Valeur | Source |
|---|---|---|
| Écart minimal détectable, qualité v2 | 14,4 pts | `bench/matrix/results/finetune/loop/round-1/T5-bench-power-audit.md` |
| Écart minimal détectable, inventions | 3,6 sur 36 | idem |
| Cas à faits contestés | 11 sur 36 | le journal de mission interne (non publié), règle de décision |
| Familles absentes du banc | tests, processus, scripts, bases, node, cargo, sécurité, infra | `t5/families.json` |
| Cas en anglais | 0 | idem |

Cible v3 : **600 sorties distinctes au moins**, chacune évaluée en FR et en EN, soit **1 200 évaluations**.
Avec 600 cas appariés, l'écart minimal détectable baisse d'un facteur racine de 600/36, soit environ 4 : de l'ordre de 3,5 pts v2 et d'une invention pour 36 cas.
Estimation écrite, à mesurer par `bench/matrix/loop/bench_power.py` sur les 3 graines une fois le banc construit.

## 2. Taxonomie des familles

Ne sont retenues que les commandes dont la sortie vaut d'être dite.
Exclus : plein écran (`vim`, `less`, `top` interactif, `htop`, `tmux`), sorties vides (`cd`, `export`, `clear`), commandes de saisie (`read`, `passwd`).

| Famille (`family`) | Commandes | Erreurs typiques à couvrir |
|---|---|---|
| `vcs-git` | status, log, diff --stat, pull, push, merge, rebase, clone, checkout, stash list, branch, fetch | conflit de fusion, push refusé (non fast-forward), dépôt introuvable, authentification, HEAD détachée, fichiers non suivis écrasés |
| `build-native` | gcc, g++, clang, make, cmake, ninja, go build | erreur de compilation fichier:ligne, symbole non défini à l'édition de liens, en-tête absent, cible make absente, CMake sans paquet |
| `js-node` | npm/pnpm/yarn install, run build, node script, npx, tsc | ERESOLVE, module introuvable, erreur TypeScript TS2322, script absent, vulnérabilités d'audit, exception Node avec pile |
| `python` | pip/uv install, python script, venv, poetry | traceback avec fichier:ligne, ModuleNotFoundError, conflit de versions, externally-managed-environment, SyntaxError |
| `rust-go` | cargo build/run/check, go mod tidy, go run | erreur E0308 avec emplacement, emprunt, crate introuvable, module Go manquant |
| `tests` | pytest, jest, vitest, go test, cargo test, unittest, npm test | N échecs sur M, nom du test en échec, assertion attendu/obtenu, délai dépassé, aucun test collecté |
| `lint-format` | eslint, ruff, mypy, flake8, clippy, shellcheck, prettier --check | N problèmes dans K fichiers, règle et emplacement, erreurs de type |
| `packages-system` | apt list --upgradable, apt-cache policy, dpkg -l, dnf check-update, brew list/outdated/info, snap list, flatpak list | paquet introuvable, verrou dpkg, dépôt en erreur, formule absente |
| `services-logs` | systemctl status/list-units --failed/is-active, journalctl -u -n, dmesg, launchctl list, log show --last | service en échec avec code, unité introuvable, redémarrages en boucle, OOM dans le journal |
| `processes` | ps, pgrep, pidof, uptime, kill (sur processus du bac à sable), lsof -i, top -b -n1 | processus absent, permission refusée, port déjà utilisé |
| `disk-memory` | df -h, du -sh, free -h, lsblk, vm_stat, diskutil list, swapon | disque plein, montages pseudo à ignorer (tmpfs, overlay), swap saturée |
| `hardware-system` | uname -a, lscpu, lspci, lsusb, sw_vers, system_profiler (résumé), sensors, hostnamectl (anonymisé) | capteur absent, périphérique inconnu |
| `network` | ip -br a, ip route, ifconfig, ss -tlnp, netstat, ping -c, dig, nslookup, traceroute, resolvectl | hôte injoignable, nom introuvable (NXDOMAIN), perte de paquets, aucune route |
| `network-transfer` | curl -I, curl API JSON, wget, ssh (échecs), scp, rsync, nc -z | connexion refusée, certificat invalide, 404/500, délai, clé d'hôte changée, permission refusée (publickey) |
| `permissions-users` | chmod, chown, sudo -l, id, groups, ls -l sur fichier protégé, umask | permission refusée, opération non permise, utilisateur inconnu |
| `containers` | docker ps/images/logs/build/run, docker compose up/ps/logs, podman, kubectl get/describe/logs | image introuvable, port occupé, conteneur qui redémarre, CrashLoopBackOff, ImagePullBackOff, démon absent |
| `data` | sqlite3, psql, mysql, jq, csvlook, redis-cli | table absente, erreur de syntaxe SQL, connexion refusée, JSON invalide |
| `files` | ls, find, grep, rg, wc, tar, zip/unzip, rsync local, cp, mv, rm (bac à sable), cat, head, tail, diff | fichier introuvable, répertoire non vide, archive corrompue, aucun résultat |
| `shell-scripts` | bash script.sh, sh -n, set -e qui échoue, commande introuvable, boucle avec sortie mêlée | command not found, ligne N: erreur de syntaxe, variable non liée |
| `infra` | terraform plan/validate, ansible-playbook --check, gh run list | plan avec N ajouts/modifications/destructions, variable manquante, hôte injoignable |
| `history-qa` | sessions de 2 à 12 commandes issues des familles ci-dessus, puis une question | réponse absente de l'historique, valeur dans une commande ancienne, comparaison entre deux commandes |

Chaque famille couvre les deux OS quand l'outil existe sur les deux (`ls`, `grep`, `ping`, `ps`, `df` diffèrent entre BSD et GNU).

## 3. Pondération

Aucune source publique ne mesure la fréquence des **sorties** de terminal.
La pondération combine donc trois signaux, puis applique un facteur « vaut d'être dit ».

| Source | Ce qu'on en tire |
|---|---|
| Stack Overflow Developer Survey 2022, « Version control » (https://survey.stackoverflow.co/2022/#version-control) | git utilisé par environ 94 % des répondants : famille la plus universelle |
| Stack Overflow Developer Survey 2024, « Other tools » (https://survey.stackoverflow.co/2024/technology) | Docker, npm, pip, Homebrew, Make, Yarn, Kubernetes, apt en tête des outils cités : dev JS et Python, conteneurs, paquets |
| Stack Overflow Developer Survey 2024, « Operating system » (même page) | macOS et Linux sont tous deux des OS de travail majeurs : les deux OS sont couverts |
| Greenberg, S. (1988). *Using Unix: Collected traces of 168 users.* Research Report 88/333/45, University of Calgary | distribution zipfienne : une poignée de commandes (`ls`, `cd`, `cat`, éditeur, `make`) domine ; les fichiers pèsent lourd |
| Lin, X. V. et al. (2018). *NL2Bash: A Corpus and Semantic Parser for Natural Language Interface to the Linux Operating System.* LREC 2018 | `find`, `grep`, `xargs`, `ls`, `tar`, `wc` dominent les commandes d'une ligne des administrateurs |
| T5, `t5/families.json` (mix K3, 3 323 exemples, historiques réels de steph) | réseau, compilation, outils texte, paquets, listage entre 8 et 11 % chacun ; tests quasi absents (1) |

Facteur « vaut d'être dit » : un échec pèse plus qu'un succès, car c'est là qu'une personne aveugle a besoin de la phrase exacte.
D'où **45 % d'échecs** au moins, et les tests, compilateurs et journaux au-dessus de leur fréquence brute.

Plafond : **10 % par famille**. Plancher : **8 cas** par famille, 4 en `infra`.

| Famille | Cas retenus | Part | Raison |
|---|---:|---:|---|
| `vcs-git` | 40 | 6,7 % | universel (SO 2022) |
| `tests` | 40 | 6,7 % | trou du mix et du banc ; échecs très fréquents en dev |
| `files` | 40 | 6,7 % | Greenberg, NL2Bash |
| `build-native` | 30 | 5,0 % | 10 % du mix K3 |
| `js-node` | 30 | 5,0 % | npm en tête SO 2024 |
| `python` | 30 | 5,0 % | pip en tête SO 2024 |
| `containers` | 30 | 5,0 % | Docker en tête SO 2024 |
| `packages-system` | 30 | 5,0 % | 9,4 % du mix |
| `services-logs` | 30 | 5,0 % | aucun `journalctl` au banc 36 |
| `network` | 30 | 5,0 % | 10,8 % du mix, déjà bien couvert ailleurs |
| `disk-memory` | 25 | 4,2 % | |
| `network-transfer` | 25 | 4,2 % | ssh, curl : erreurs fréquentes |
| `rust-go` | 20 | 3,3 % | trou du mix |
| `lint-format` | 20 | 3,3 % | |
| `processes` | 20 | 3,3 % | absent du banc 36 |
| `data` | 20 | 3,3 % | absent du banc 36 |
| `hardware-system` | 15 | 2,5 % | déjà couvert par le Speak Bench |
| `shell-scripts` | 15 | 2,5 % | |
| `permissions-users` | 12 | 2,0 % | |
| `infra` | 8 | 1,3 % | rare, mais absent partout |
| **Résumés** | **510** | **85 %** | |
| `history-qa` | 90 | 15 % | dont un tiers « absent de l'historique » |
| **Total** | **600** | 100 % | |

Répartitions transverses, contrôlées par `tools/validate.py` sur le banc entier :

| Axe | Cible |
|---|---|
| OS | Linux 60 %, macOS 40 % |
| Langue de la sortie (`output_lang`) | FR 25 % au moins (locale `fr_FR.UTF-8` quand l'outil est traduit : coreutils, apt, git, dnf), EN 65 %, sans texte 10 % |
| Statut | échec 45 à 55 %, succès 45 à 55 %, dont 10 % de succès avec avertissements |
| Longueur (`length_class`) | court 30 %, moyen 35 %, long (plus de 60 lignes) 35 % |
| Difficulté | facile 25 %, moyen 45 %, difficile 30 % |
| Origine | réelle 80 % au moins, reconstruite 20 % au plus |

Pondération au niveau ÉCRIT : estimation argumentée, non mesurée sur des historiques de personnes aveugles.

## 4. Format d'un cas

Schéma exact : `bench/matrix/v3/schema.json` (JSON Schema 2020-12). Une ligne JSON par cas.

```
bench/matrix/v3/
  DESIGN.md, schema.json
  cases/dev/<family>.jsonl      40 %, lisible
  cases/test/<family>.jsonl     60 %, caché (section 6)
  fingerprints.txt              empreintes des sorties dev et test, pour filtrer les corpus
  tools/                        capture.py, build_inputs.py, validate.py, leak_check.py, split.py
```

Champs principaux :

| Champ | Contenu |
|---|---|
| `id` | `v3-<famille>-<nnnn>`, jamais réutilisé |
| `family`, `subfamily`, `os`, `distro`, `output_lang` | taxonomie, OS, langue de la sortie elle-même |
| `origin`, `source` | `real` ou `reconstructed` ; classe de machine (`i5`, `a1000-sandbox`, `mac-tmphome`, `public`), date, lot, locale ; URL et licence si reconstruite |
| `cmd`, `exit`, `status`, `error_type`, `duration_s`, `nlines`, `output_raw` | capture anonymisée, stdout et stderr mêlés comme à l'écran, ANSI retiré |
| `history`, `question`, `answer_in_history` | questions sur l'historique : 2 à 12 commandes, question FR et EN |
| `input.fr`, `input.en` | messages [système, utilisateur] du format de production B3, générés par code (section 4.1) |
| `facts.need`, `facts.never` | faits attendus et interdits, FR et EN (section 5) |
| `reference.fr`, `reference.en` | phrase de référence qui obtient 100 % |
| `difficulty`, `length_class`, `max_words` | 20 mots en résumé, 30 en question |
| `review`, `anonymization`, `leak_check`, `canary` | double lecture, PII à 0, contrôle de fuite, chaîne canari |

### 4.1 Entrée de production

`tools/build_inputs.py` construit `input` depuis `src/steph` à un commit fixé (`input.builder.steph_commit`) :

- résumé : `prompts.finetuned_summary_messages(cmd, exit, duration, output, language)`, système `SUMMARY_SYSTEM_FINETUNED` / `_EN` (copie de `TRAIN_SYSTEM`), sortie passée par `digest()` plafonné à **587 caractères** ;
- question : format de `server._ask` en profil affiné : `QA_SYSTEM` / `QA_SYSTEM_EN`, historique, accusé, puis « (dossier actuel : {cwd}) » et la question ; blocs d'historique de 2 500 caractères, budget 8 000 (`FINETUNED_QA_BUDGET_CHARS`), coupe au fil de l'eau (`v3lib.rebuild_qa_input`).

Si `digest()` change, on régénère `input` et on relance `validate.py` : un fait qui n'est plus dans l'entrée devient invalide.

## 5. Règle des faits attendus FR et EN

Mise en correspondance : regex Python sur la réponse après `plain()` de `bench/matrix/score.py` (minuscules, accents retirés, apostrophe droite).
Score d'un cas : identique à `rescore.score_case` ; un `never` touché donne 0 ; une réponse au-delà de `max_words` est multipliée par 0,8.

1. **Un fait = une information utile à l'oreille** : le nombre d'échecs, le test en échec, fichier:ligne, l'espace libre, le service en échec. Au plus 4 par cas, 2 à 3 d'habitude.
2. **Chaque fait existe en FR et en EN.** Nombres, noms de fichiers, de tests, de paquets identiques dans les deux. Seuls les mots changent : `echec|echoue|rate` contre `fail(ed|ing|s)?`.
3. **Synonymes par alternatives** dans la liste du fait : `\b3 (tests? )?(en )?echec`, `3 tests? echoue`, `trois tests?`. Nombres acceptés en chiffres et, jusqu'à 10, en lettres.
4. **Tout fait requis figure dans l'entrée** (`input.fr` et `input.en`, donc après `digest()`). `validate.py` vérifie que chaque littéral requis (nombre, nom) y apparaît. Ce que le digest a coupé ne peut pas être exigé.
5. **Jamais le mot de statut** : la production dit « succès » ou « échec » avant l'appel au modèle (P9). Un fait ne l'exige pas.
6. **`never` vise les inventions plausibles** : une valeur absente de l'entrée mais tentante (le total au lieu du libre, un autre fichier de la pile, l'interface `lo`, un nombre de lignes pris pour un nombre d'éléments). Les interdits globaux restent dans `scoring.json` (raisonnement, markdown, balises).
7. **Aucune valeur recopiée d'un exemple de prompt** : les faits ne reprennent aucun nom ni nombre des exemples de `prompts.py`.
8. **Questions** : si `answer_in_history` est faux, le fait requis est la formule d'absence (`pas dans l'historique|introuvable|aucune trace`, `not in the history|no record|not found`), et `never` interdit toute valeur de réponse.
9. **Double lecture** : l'auteur du lot écrit les faits, un second lecteur indépendant les relit sur l'entrée seule. Désaccord : `review.contested = true`, cas rapporté à part, jamais décisif seul.
10. **La référence obtient 100 %** dans les deux langues, en `max_words` au plus : vérifié par `validate.py`.

## 6. Split

| Split | Part | Accès |
|---|---|---|
| `dev` | 40 % | lisible, réglage des prompts et des faits permis |
| `test` | 60 % | caché : seul le harnais du Juge le lit ; jamais montré à un agent qui entraîne, étiquette, compose un corpus ou écrit des exemples |

- Affectation déterministe par `tools/split.py` : stratifiée par famille, origine et `output_lang`, tirage par sha256 de l'`id` et d'un sel fixé.
- Les cas d'une même capture (même projet, même session) tombent dans le même split. Une question sur l'historique qui réutilise des sorties (`case_ref`) reste dans leur split.
- Le test vit dans le dépôt privé, avec la chaîne canari de `schema.json`. Tout constructeur de corpus filtre la canari et `fingerprints.txt`. La garantie est procédurale : chaque brief d'agent d'entraînement interdit `bench/matrix/v3/cases/test/`.

## 7. Fuite vers l'entraînement

Corpus comparés : RTX 3080 `/root/steph-ft/data/final`, portable A1000 `/root/steph-ft/k3/mix`, plus le Speak Bench v1 et le banc 36.
Le corpus ne quitte jamais son hôte : on y copie `leak_check.py` et les empreintes des cas (des hachages, pas de texte), et seuls ids et scores reviennent.
Sur RTX 3080, rien n'est écrit sous `/var`.

Méthode `v3-fp1` :

1. Normaliser chaque ligne : minuscules, chiffres remplacés par `0`, hexa de 6 caractères ou plus par `h`, chemins par `/p`, espaces réduits.
2. Empreinte de ligne : sha1 tronqué ; empreinte de sortie : ensemble des empreintes de lignes, plus les shingles de 5 mots.
3. Commande normalisée : binaire et sous-commande, arguments masqués.
4. **Écarté** si Jaccard de lignes ≥ 0,5, ou shingles ≥ 0,6, ou (même commande normalisée et Jaccard de lignes ≥ 0,3).
5. Doublons internes au banc : deux cas à Jaccard de lignes ≥ 0,7 : on garde un seul.

On capture 10 à 15 % de plus que la cible pour absorber les rejets de fuite, de doublons et d'anonymisation.

## 8. Capture

| Machine (`source.machine`) | Règles |
|---|---|
| `i5` (Linux) | lecture seule ; vérifier avant chaque rafale qu'aucun `llama-server` ne tourne (`pgrep -x llama-server`), sinon attendre ; commandes courtes, `timeout 10` ; aucun `apt install`, aucun redémarrage de service |
| `a1000-sandbox` (Linux, RTX A1000) | tout sous `/root/steph-ft/bench-v3/` : faux projets git, npm, python, cargo, go, compilations ratées et tests en échec volontaires ; dépendances confinées au projet (venv, `node_modules`, `target/`), jamais système, jamais `-g`, jamais `sudo` ni `apt` |
| `mac-tmphome` (macOS) | `HOME` temporaire dans le scratchpad, config git propre à ce HOME ; `brew` en lecture seule (`list`, `outdated`, `info`, jamais `update`) ; `launchctl list`, `log show --last 1m` en lecture |
| `public` | sorties documentées (docs officielles, tldr-pages CC BY 4.0, docs Kubernetes CC BY 4.0) quand la licence le permet ; `origin = reconstructed`, URL et licence dans `source` |

Interdits partout : commande destructive hors bac à sable, installation système, capture sur RTX 3060 ou serveur Xeon.
Locale : une capture en `C.UTF-8` et, quand l'outil est traduit, une seconde en `fr_FR.UTF-8` si la locale existe déjà (`locale -a`), sans rien installer. Les deux ne comptent que si leurs sorties diffèrent au-delà de la langue ; sinon on garde l'une des deux.

Anonymisation avant tout commit : `bench/matrix/finetune/clean_pii.py` puis `audit_pii.py` à 0 (liste privée `~/.config/steph/pii_names.tsv`, jamais affichée ni copiée), puis lecture à la main de 10 % des cas de chaque lot (`anonymization.manual_sample`).
Aucun nom d'hôte, utilisateur, IP réelle, chemin personnel, e-mail, numéro de série. IP de remplacement dans les plages de documentation (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24).

## 9. Lots

Cible de capture = cible retenue plus 12 % environ. Les lots 1 à 12 tournent en parallèle ; le lot 13 part après eux, puisqu'il réutilise leurs sorties.

| Lot | Familles | Retenus | Capturés | Machines | Contenu clé |
|---|---|---:|---:|---|---|
| L01 | `vcs-git` | 40 | 45 | a1000-sandbox, mac-tmphome | conflits, push refusé, rebase, logs, diff --stat ; locale FR |
| L02 | `build-native`, `rust-go` | 50 | 56 | a1000-sandbox | gcc/clang/make/cmake, cargo E0xxx, go build, liens ratés ; sorties longues |
| L03 | `js-node` | 30 | 34 | a1000-sandbox, mac-tmphome | npm/pnpm install et build, tsc, ERESOLVE, piles Node |
| L04 | `python` | 30 | 34 | a1000-sandbox, mac-tmphome | pip/uv, tracebacks, externally-managed, venv |
| L05 | `tests` | 40 | 45 | a1000-sandbox | pytest, jest, vitest, go test, cargo test : succès, N échecs, délais, rien collecté |
| L06 | `lint-format`, `shell-scripts` | 35 | 40 | a1000-sandbox, mac-tmphome | eslint, ruff, mypy, clippy, shellcheck ; scripts bash qui échouent |
| L07 | `packages-system` | 30 | 34 | i5, mac-tmphome, public | apt list/policy, dpkg -l, brew list/outdated ; dnf reconstruit |
| L08 | `services-logs`, `processes` | 50 | 56 | i5, mac-tmphome | systemctl, journalctl, dmesg, launchctl, log show, ps, lsof, uptime |
| L09 | `disk-memory`, `hardware-system` | 40 | 45 | i5, mac-tmphome | df, du, free, lsblk, vm_stat, diskutil, lscpu, lspci, sw_vers |
| L10 | `network`, `network-transfer` | 55 | 62 | i5, a1000-sandbox, mac-tmphome | ip, ss, ping, dig, curl vers serveur local du bac à sable, ssh refusé, rsync |
| L11 | `containers`, `infra` | 38 | 43 | i5, a1000-sandbox, public | docker ps/logs/compose si présents en lecture ; kubectl et terraform reconstruits |
| L12 | `files`, `data`, `permissions-users` | 72 | 81 | a1000-sandbox, mac-tmphome | find, grep, tar, rsync, cp/mv/rm en bac à sable, sqlite3, jq, psql reconstruit, chmod refusé |
| L13 | `history-qa` | 90 | 100 | a1000-sandbox, mac-tmphome | sessions de 2 à 12 commandes ; 60 réponses présentes, 30 absentes |
| L14 (X2b) | toutes, sorties de plus de 60 lignes | 179 | 184 | a1000-sandbox, mac-tmphome | compilations, configure GNU, suites de tests, lint, tracebacks, fichiers, anglais |
| L15 (X2b) | toutes, locale `fr_FR.UTF-8` | 202 | 210 | a1000-sandbox | apt, make de paquets GNU, coreutils verbeux, scripts bash en français, wget |
| **Total** | | **600** | **675** | | |

Chaque lot livre : cas au schéma, `validate.py` vert, PII à 0, fuite contrôlée, faits relus deux fois.
Après les lots : validation globale des répartitions (section 3), `split.py`, juge A7 revalidé 6/6 en FR et sur 6 cas de contrôle EN (`judge_lib_en.py`), puis mesure de puissance sur 3 graines.

## 10. Niveau de preuve de cette conception

| Affirmation | Niveau | Preuve | Non vérifié |
|---|---|---|---|
| `schema.json` est un JSON Schema 2020-12 valide | VÉRIFIÉ | `jsonschema.Draft202012Validator.check_schema` ; un cas exemple passe, un `max_words` à 30 en résumé est refusé | les outils `tools/*.py` n'existent pas encore |
| 600 cas donnent un écart minimal détectable d'environ 3,5 pts | ÉCRIT | calcul en racine de n depuis T5 | à mesurer avec `bench_power.py` sur le banc construit |
| La pondération reflète l'usage réel | ÉCRIT | sources de la section 3 | aucun historique de personne aveugle mesuré ; enquêtes sans fréquence de sorties |
| Les machines de capture ont les outils cités | ÉCRIT | aucune | présence de docker, psql, kubectl, locale FR sur i5 et portable A1000 à vérifier par chaque lot |
