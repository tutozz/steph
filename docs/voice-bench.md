# Bench des voix françaises

Mesuré le 2026-09-26 sur un MacBook Pro M3 Pro (18 Go), CPU seul, à chaud (voix préchargée comme dans `Speaker`).
Scripts et données brutes : scratchpad de session `voicebench/` (`bench.py`, `asr.py`, `keywords.py`), non versionnés.

## Conclusion

- **La voix n'est pas la cause principale.** Whisper comprend siwis-medium aussi bien que les autres candidats. Les pertes viennent surtout du texte envoyé : `Mo`, `git push`, `commits`, `/usr`, `vim-common`, `TypeScript`.
- **Corriger `normalize_for_speech` rapporte plus que changer de moteur.** Sur les mêmes voix, un texte corrigé à la main fait passer le score de 20/29 à 22-25/29.
- **Piper reste le bon moteur** sur tous les tiers : premier son sous 0,2 s, streaming phrase par phrase, aucune dépendance nouvelle.
- **Kokoro, Pocket TTS et Supertonic ne valent pas l'intégration** aujourd'hui : premier son à 1 s ou plus, ou phrases tronquées, pour une intelligibilité égale ou pire.

## Méthode

- 8 phrases types steph, passées par `normalize_for_speech` actuel (ce que steph prononce vraiment).
- Latence : temps entre l'appel de synthèse et le premier bloc audio disponible, médiane et max sur les 8 phrases.
- Facteur temps réel (RTF) : temps de synthèse total / durée audio. Sous 1, plus rapide que la parole.
- RAM : pic RSS du processus Python (modèle + runtime).
- Intelligibilité : aller-retour ASR. Chaque clip est transcrit par Whisper large-v3-turbo, puis on compte 29 mots-clés utiles retrouvés (ex. `127`, `introuvable`, `git`, `push`, `commits`, `usr`, `npm`, `critique`).
- Variante « texte corrigé » : mêmes phrases réécrites à la main selon les corrections de la dernière section, sur les 6 meilleures voix.

L'aller-retour ASR est un **proxy**, pas une écoute humaine. Il mesure si les mots sont reconnaissables, pas le confort ni le naturel. L'écoute des MP3 ci-dessous reste la décision.

## Tableau comparatif

| Voix | Moteur | Licence voix | Taille modèle | Chargement | 1er son (méd. / max) | RTF | RAM | Mots-clés (texte actuel) | Mots-clés (texte corrigé) |
|---|---|---|---|---|---|---|---|---|---|
| **fr_FR-siwis-medium** (actuelle) | Piper | CC-BY 4.0 | 63 Mo | 0,6 s | 0,09 / 0,14 s | 0,027 | 262 Mo | 20/29 | 22/29 |
| fr_FR-siwis-low | Piper | CC-BY 4.0 | 28 Mo | 0,6 s | 0,05 / 0,08 s | 0,016 | 212 Mo | 16/29 | non testé |
| **fr_FR-tom-medium** | Piper | AGPLv3 (données) | 64 Mo | 0,5 s | 0,18 / 0,25 s | 0,046 | 387 Mo | 20/29 | 23/29 |
| **fr_FR-upmc-medium** (jessica, id 0) | Piper | CC-BY-SA 4.0 | 77 Mo | 0,5 s | 0,09 / 0,17 s | 0,031 | 278 Mo | 19/29 | **24/29** |
| fr_FR-gilles-low | Piper | CC0 | 63 Mo | 0,5 s | 0,09 / 0,12 s | 0,020 | 279 Mo | 18/29 | 18/29 |
| fr_FR-mls-medium (locuteur 0) | Piper | CC-BY 4.0 | 77 Mo | 0,3 s | 0,11 / 0,15 s | 0,027 | 283 Mo | 6/29 | non testé |
| ff_siwis, int8 | Kokoro 82M (kokoro-onnx) | Apache 2.0 (poids), CC-BY 4.0 (SIWIS) | 92 + 28 Mo | 0,4 s | 1,61 / 2,76 s | 0,442 | 423 Mo | 20/29 | non testé |
| ff_siwis, fp32 | Kokoro 82M (kokoro-onnx) | idem | 310 + 28 Mo | 0,8 s | 1,11 / 1,88 s | 0,306 | 558 Mo | 21/29 | non testé |
| estelle, français | Pocket TTS (Kyutai, 100M) | MIT (code), CC-BY 4.0 (modèle), voix : provenance non trouvée | 227 Mo + torch 553 Mo | 4,6 s | 0,04 / 0,05 s | 0,136 | 856 Mo | 15/29 | non testé |
| F1 | Supertonic 3 (99M) | OpenRAIL-M (modèle), MIT (code) | 380 Mo | 0,3 s | 1,12 / 2,29 s | 0,222 | 508 Mo | 18/29 | non testé |
| M1 | Supertonic 3 (99M) | idem | 380 Mo | 0,3 s | 0,97 / 1,78 s | 0,202 | 523 Mo | 20/29 | 23/29 |
| Thomas (secours actuel) | macOS `say` | système Apple | inclus | 0 | 0,95 / 3,50 s (fichier) | 0,295 | n/a | **22/29** | **25/29** |
| Audrey (Enhanced) | macOS `say` | système Apple | inclus | 0 | 0,93 / 1,05 s (fichier) | 0,204 | n/a | 20/29 | non testé |

Notes :

- Pour `say`, la latence mesurée inclut l'écriture d'un fichier complet. En lecture directe, `say` parle plus tôt ; non mesuré.
- Pocket TTS **tronque les phrases courtes** : 0,7 s d'audio pour « Erreur 127 : commande introuvable. » contre 3,0 s chez Piper. Whisper y entend « Alors, d'où sont ces... ».
- Supertonic : dépôt GitHub archivé le 2026-09-09, lecture seule. Pas de streaming, la phrase entière est calculée avant le premier son.
- Kokoro invente des mots sur les anglicismes : « npm install » devient « NPM et Ninstolfre », « title » devient « intitle for ».
- mls-medium avec le locuteur par défaut est inutilisable : « Terminé en 1 minute 24 » devient « l'internet ».
- tom-medium est échantillonné en 44,1 kHz, d'où sa RAM et son RTF plus élevés.

## Écoute

Un dossier par voix dans `docs/voice-bench/`, un MP3 par phrase (`1.mp3` à `8.mp3`), 5,8 Mo au total.
Les dossiers `fixed-*` contiennent la variante « texte corrigé ».

| n | Phrase envoyée à steph | Texte corrigé à la main (dossiers `fixed-*`) |
|---|---|---|
| 1 | Erreur 127 : commande introuvable. | identique |
| 2 | Terminé en 1 minute 24. 12 paquets mis à jour. | Terminé en une minute 24 secondes. 12 paquets mis à jour. |
| 3 | Question : 24 Mo d'espace disque supplémentaires seront utilisés. Voulez-vous continuer ? oui ou non, oui par défaut | 24 mégaoctets |
| 4 | Erreur TypeScript : la propriété titel n'existe pas, utilisez title. | Erreur taïpe script : la propriété titel, t i t e l, n'existe pas, utilisez title, t i t l e. |
| 5 | Dossier /usr/local/bin | Dossier slash u s r slash local slash bin |
| 6 | git push a échoué : rejeté, la branche distante a des commits que vous n'avez pas. | guite pouche a échoué : [...] des commites [...] |
| 7 | 35 pour cent, dépaquetage de vim-common. | 35 pour cent, dépaquetage de vim tiret common. |
| 8 | npm install : 3 vulnérabilités, dont 1 critique. | N P M install : 3 vulnérabilités, dont une critique. |

Ordre d'écoute conseillé : `piper-siwis-medium` (actuelle), `piper-upmc-medium`, `piper-tom-medium`, `macos-thomas`, puis leurs équivalents `fixed-*`.

## Recommandation par tier

Seul le Mac M3 Pro a été mesuré. Les autres tiers sont extrapolés à partir des RTF : un CPU faible peut être 5 à 10 fois plus lent, ce qui laisse Piper medium sous 0,3 de RTF.

| Tier (`src/steph/profiles/`) | Voix par défaut | Choix manuels proposés | Raison |
|---|---|---|---|
| `cpu` (CPU faible) | fr_FR-siwis-medium | upmc-medium, siwis-low en dernier recours | RTF 0,027 ; siwis-low perd 4 mots-clés pour gagner peu |
| `integrated` | fr_FR-upmc-medium | siwis-medium, tom-medium | meilleur score après correction du texte, latence de siwis |
| `dedicated` | fr_FR-tom-medium | upmc-medium, siwis-medium | voix masculine 44,1 kHz, coût négligeable sur une machine puissante ; le GPU n'apporte rien à Piper |
| `apple` | fr_FR-tom-medium | voix système `say` (Thomas, Audrey Enhanced), upmc-medium | `say` donne le meilleur score ASR, sans téléchargement, mais la décision se prend à l'écoute |

Piste d'intégration, hors de ce bench : une clé `voice` dans la section `[settings]` de chaque profil `.toml`, surchargeable par `config.toml` et `STEPH_VOICE`, comme les autres réglages. Voix disponibles au téléchargement : `https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR`.

À écarter : mls-medium (locuteur 0), gilles-low (hallucinations sur les chemins), Kokoro, Pocket TTS, Supertonic. Les licences tom-medium (AGPLv3 sur les données) et upmc (CC-BY-SA) restent compatibles avec un usage non commercial ; l'attribution est à mentionner dans le README si elles sont distribuées.

## Corrections de normalisation recommandées

Phonèmes lus avec l'espeak-ng de Piper (`EspeakPhonemizer().phonemize("fr", ...)`), le même que celui de toutes les voix Piper.

| # | Défaut | Aujourd'hui | Correction proposée |
|---|---|---|---|
| 1 | Unités d'octets lues comme des syllabes | `24 Mo` : « vingt-quatre mo », Whisper entend « mots » sur 13 voix sur 13 | `Ko/Mo/Go/To`, `kB/MB/GB`, `KiB/MiB/GiB` après un nombre : kilooctets, mégaoctets, gigaoctets, téraoctets |
| 2 | « 1 » toujours masculin | `1 minute`, `1 erreur`, `1 seconde`, `1 heure` : « un » | `1` devant un nom féminin connu : « une » (liste courte : minute, seconde, heure, erreur, vulnérabilité, ligne, requête, dépendance) |
| 3 | Durées tronquées | `1 minute 24` : on ne sait pas que 24 sont des secondes | `N minute(s) M` : ajouter « secondes » ; `1m24s`, `850ms`, `2.5s` : développer |
| 4 | Anglicismes du développement lus en français | `git` : « ji », `GitHub` : « ji eub », `commits` : « comi », `TypeScript` : « tipe scripte », `README` : anglais, `build` : « bu-ilde », `null` : anglais | Lexique de réécriture phonétique : git → guite, push → pouche, commit(s) → comite(s), TypeScript → taïpe script, GitHub → guite hub, README → ride mi, build → bilde, null → nul. À régler à l'oreille : Whisper entend encore « Guide » pour « guite » |
| 5 | Barre oblique initiale perdue | `/usr/local/bin` : « usr slash local slash bin », le premier `/` disparaît | Traiter aussi le `/` en début de chemin (« slash » ou « racine ») |
| 6 | Abréviations de chemin illisibles | `usr` : « usr » en une syllabe | Épeler les segments courts sans voyelle ou connus : usr → u s r, tmp → temp, etc, lib, dev, opt |
| 7 | Point des noms de fichiers muet | `config.toml` : « config toml », `tts.py:120` : « tts py cent vingt » | `nom.ext` : « nom point ext » ; `fichier:ligne` : « fichier, ligne N » |
| 8 | Identifiants de code indistinguables | `titel` et `title` : Whisper entend « title » deux fois, le message perd son sens | Garder la trace des backticks (aujourd'hui supprimés) et épeler les identifiants courts d'un message d'erreur : « titel, t i t e l » |
| 9 | Tiret des noms de paquets avalé | `vim-common` : « vimcommon », entendu « villes communes », « vie commun » | Tiret entre deux lettres dans un nom de paquet : espace ou « tiret » |
| 10 | Sigles en capitales lus en anglais ou collés | `EACCES` : « iksiz », `GPU` : « gpu » en un mot, `npm` passe mais `pnpm` hésite | Capitales de 2 à 6 lettres absentes du lexique : épeler lettre par lettre (N P M, G P U) |
| 11 | Symboles supprimés par le nettoyage Markdown | `x = 3 * 4` : « x = 3 4 », `2>&1` : « 2 &1 » | Ne retirer `*` et `>` qu'en début de ligne ou autour de mots (Markdown), pas entre deux nombres ; `2>&1` : « erreurs vers la sortie » |
| 12 | Chemins Windows ignorés | `C:\Users\x` : antislashs conservés, lus au hasard | `\` entre deux mots : « antislash » ou « slash » |

## Piège découvert pendant le bench

**Piper devient muet si son dossier `espeak-ng-data` a un chemin trop long.**
Avec un venv à 171 caractères, espeak-ng ignore le chemin passé et cherche `/Users/runner/work/piper1-gpl/.../phontab`, le chemin de compilation du wheel. Aucune exception n'atteint `Speaker` : `_speak_one` avale l'erreur, steph se tait.
Même défaut dans `espeakng_loader` (Kokoro). Un chemin à 118 caractères fonctionne.
Risque réel pour un utilisateur au `HOME` profond ou un venv installé loin. Correctifs possibles : passer `espeak_data_dir` vers un lien symbolique court, ou vérifier au démarrage (`steph doctor`) qu'une phrase test produit des échantillons.

## Non vérifié

- Écoute humaine : aucun des MP3 n'a été écouté. Le classement repose sur Whisper.
- Autres machines : CPU faible, GPU intégré, GPU dédié non mesurés.
- Latence réelle de `say` en lecture directe.
- Locuteur `pierre` (id 1) de upmc-medium et autres locuteurs de mls-medium.
- Pocket TTS avec d'autres réglages (`frames_after_eos`, modèle `french_24l`) : la troncature n'a pas été diagnostiquée.
- Licence exacte de la voix `estelle` de Pocket TTS.
