# Télémétrie et fonctionnement hors ligne (T1)

Vérification du 2026-09-28, demandée par une note interne (non publiée) (ligne 324) : le site
et le README affirment « aucune télémétrie » et « rien ne quitte votre machine ». Jusqu'ici,
l'affirmation reposait sur une lecture de code (seul appel HTTP vers `127.0.0.1`), jamais sur
un essai. Cette note documente l'essai, corrige le code, et donne la formulation à tenir.

## Méthode

| Terrain | Ce qui a été fait |
|---|---|
| Lecture de code | `src/steph/`, `scripts/install.sh`, `site/public/install` : tout appel réseau, sa cible, son déclencheur |
| Mac, `HOME` temporaire | `steph say`, `steph setup` sans TTY, `steph update --check`, session pty ; connexions surveillées par `lsof -i -P` échantillonné (0,1 à 0,3 s), corrélées au process par sa ligne de commande complète |
| Linux, i5 (`user@host`), utilisateur temporaire | `onnxruntime` + `piper-tts` (le paquet réellement utilisé par steph) installés dans un venv ; mêmes essais, connexions corrélées par `ss -tnp` + `/proc/<pid>/cmdline` ; utilisateur supprimé en fin de tâche |
| Essai « machine débranchée » | `unshare -n` (Linux, aucune interface hors `lo`, redescendue) : chargement Piper/onnxruntime observé |
| onnxruntime | lecture de `onnxruntime/Privacy.md` et des symboles du binaire compilé (`strings`) ; confirmation par la documentation officielle (`raw.githubusercontent.com/microsoft/onnxruntime`) |

`tcpdump` n'a pas pu être utilisé sans `sudo` (refusé par le noyau sur le Mac via
`ioctl(SIOCIFCREATE)`, absent sur l'i5, `apt` exclu par consigne). La corrélation
process ↔ connexion (`lsof`/`ss` + `/proc/<pid>/cmdline`) tient lieu de preuve à la place.

## Ce qui a été trouvé

### Code steph : aucun appel caché

| Composant | Réseau | Déclencheur |
|---|---|---|
| `src/steph/llm.py` | `http.client`/`urllib.request` vers `127.0.0.1:<llm_port>` uniquement | tourne en continu, jamais vers l'extérieur |
| `src/steph/voice_service.py`, `server.py`, `cli.py` | sockets Unix (`AF_UNIX`) | jamais IP |
| `scripts/install.sh`, `site/public/install` | `curl`/`git` vers `github.com`, `huggingface.co`, `astral.sh` | explicite : installation, `steph update` |
| Reste de `src/steph/` | aucun `requests`, `urllib`, `http.client` trouvé par recherche exhaustive | - |

Aucune télémétrie écrite par steph. Le réseau que `steph update` utilise (dépôt GitHub du
projet lui-même) est déclaré et attendu, pas caché : il ne contredit pas l'esprit de
l'affirmation, seulement sa lettre si elle est lue comme « zéro octet, jamais ».

### onnxruntime (dépendance de Piper) : télémétrie réelle, jamais désactivée

`piper-tts` installe `onnxruntime` 1.30.0. Le paquet embarque le SDK 1DS de Microsoft
(symboles `Microsoft::Applications::Events::TelemetrySystem`, endpoint
`https://mobile.events.data.microsoft.com/OneCollector/1.0`, confirmés par `strings` sur
`libonnxruntime.1.30.0.dylib`). Sa documentation (`Privacy.md`) dit : « Telemetry is turned
ON by default in the official builds ». `InferenceSession` (créée par `PiperVoice.load()`,
donc à chaque chargement de voix) appelle inconditionnellement
`env.GetTelemetryProvider().LogModelLoadStart/End()`. Avant correction, **rien dans steph
n'appelait `disable_telemetry_events()` ni ne posait `ORT_DISABLE_TELEMETRY`**.

Effet mesuré :

| Plateforme | Fichiers locaux créés | Connexion réseau observée |
|---|---|---|
| macOS (ce Mac) | `~/Library/Application Support/Microsoft/DeveloperTools/.onnxruntime/{deviceid,onnxruntime.db*}` | aucune, sur plusieurs essais dont un de 60 s ; cause de l'écart avec Linux **non identifiée** |
| Linux (i5 Debian 13) | `~/.cache/Microsoft/DeveloperTools/.onnxruntime/{deviceid,onnxruntime.db}` | **oui** : connexions HTTPS établies vers `20.42.73.27:443` et `13.89.179.12:443`, correspondant à `mobile.events.data.microsoft.com` (résolu sur la même machine : `20.42.65.84`, derrière un traffic manager Azure qui distribue plusieurs IP) |

C'est exactement la base trouvée après `steph uninstall` en B8b (`docs/setup-ux.md`) : elle
n'est pas un résidu bénin, elle est la preuve locale (identifiant d'appareil + file
d'attente) d'un mécanisme qui, au moins sur Linux, envoie réellement des données hors de la
machine. « Aucune télémétrie » était donc **faux** avant cette correction, au moins sur
Linux ; non tranché sur macOS.

### Hors ligne : vrai pour la fonction, pas pour le silence

Dans un espace de noms réseau Linux sans aucune interface (`unshare -n`, seul `lo`,
descendu), Piper/onnxruntime charge et fonctionne normalement : la synthèse vocale ne
dépend pas du réseau. « steph fonctionne hors ligne » est donc vrai pour l'usage — mais
avant cette correction, la machine n'était pas silencieuse pour autant dès que le réseau
existait : elle tentait de joindre Microsoft en tâche de fond, sans y parvenir seulement là
où il n'y avait pas de réseau.

## Correction apportée

| Fichier | Changement |
|---|---|
| `src/steph/tts.py` | pose `ORT_DISABLE_TELEMETRY=1` à l'import du module, avant toute importation de `piper`/`onnxruntime` ; appelle `onnxruntime.disable_telemetry_events()` juste avant `PiperVoice.load()` (défense en profondeur) |
| `src/steph/uninstall.py` | `onnxruntime_telemetry_dir()` (chemin selon la plateforme) ajoutée à la liste des dossiers supprimés par `steph uninstall`, pour nettoyer un reste d'avant cette correction |
| `tests/test_telemetry.py` | 6 tests : variable posée à l'import, appel de désactivation effectif au chargement d'une vraie voix, garde-fou anti-connexion non-loopback (+ preuve que le garde-fou détecterait une vraie fuite), nettoyage par `steph uninstall`, chemin selon la plateforme |

Vérifié après correction, sur ce Mac, `HOME` temporaire : plus aucun fichier créé sous
`Library/Application Support/Microsoft` au chargement d'une voix. Non ré-essayé sur Linux
après correction (utilisateur temporaire déjà supprimé) : la disparition des fichiers
locaux sur Mac, plus la garantie documentée d'`ORT_DISABLE_TELEMETRY` (empêche la création
du transmetteur avant même l'initialisation), fondent la confiance dans le correctif, mais
la connexion réseau elle-même n'a pas été ré-observée absente sur Linux après correction.

## Verdict et formulation publique recommandée

**« Aucune télémétrie »** ne peut pas rester telle quelle sans la correction ci-dessus : elle
était fausse sur Linux avant elle. Après correction, l'affirmation redevient défendable pour
le code de steph lui-même et pour onnxruntime tel qu'il est désormais configuré, à condition
que la formulation ne prétende pas à un audit de chaque dépendance transitive future.

**« Rien ne quitte votre machine » / « Nothing leaves your machine »** reste vrai pour le
modèle de langue et la voix (servis en local, `127.0.0.1`), mais est trop absolu tel quel :
`steph update` contacte volontairement GitHub, à la demande de la personne. Garder la phrase
comme titre d'intention, mais la nuancer dans le paragraphe qui suit.

Formulation recommandée, à la place de la ligne actuelle :

> FR — Aucune télémétrie : ni dans le code de steph, ni dans les dépendances qu'il configure
> (la télémétrie d'onnxruntime, utilisée par la voix, est désactivée). Le modèle et la voix
> tournent en local. Le seul réseau que steph utilise est celui que vous demandez : installer
> ou mettre à jour.
>
> EN — No telemetry: not in steph's own code, not in the dependencies it configures
> (onnxruntime's telemetry, used by the voice, is disabled). The model and the voice run
> locally. The only network steph uses is the one you ask for: installing or updating.

Si la formulation courte du site (« Aucune télémétrie. Aucun compte. Aucune clé d'API. »)
doit rester courte, la nuance sur `steph update` peut vivre dans le README (déjà plus
détaillé) plutôt que sur la page d'accueil ; mais la clause « ni dans les dépendances qu'il
configure » doit apparaître quelque part de public, sans quoi l'affirmation reste incomplète
au sens strict.

## Non vérifié

- Pourquoi aucune connexion n'a été observée sur macOS alors que le mécanisme et le code
  sont identiques à ceux de Linux (build différente du SDK 1DS, filtrage réseau propre à ce
  Mac, ou autre cause non identifiée).
- Le correctif n'a pas été re-testé sur Linux après application (utilisateur temporaire déjà
  supprimé) : la preuve de non-régression réseau post-correctif vient de macOS et de la
  documentation d'onnxruntime, pas d'une nouvelle mesure Linux.
- `tcpdump` n'a pas pu confirmer ou infirmer une tentative de connexion bloquée en amont
  (DNS résolu puis connexion refusée par un pare-feu, par exemple) sur le Mac : seule
  l'absence d'entrée `lsof`/`ss` a été observée.
- Autres dépendances que `piper-tts`/`onnxruntime` non auditées pour une télémétrie propre
  (recherche limitée à `requests`/`urllib`/`socket`/`http.client` dans `src/steph/` et au
  binaire onnxruntime lui-même).
