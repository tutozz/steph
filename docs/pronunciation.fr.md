# Prononciation des sigles, commandes et mots anglais

[English](pronunciation.md)

Mesuré le 2026-09-26 et 2026-09-27 sur le MacBook Pro M3 Pro, CPU seul.
Code : `src/steph/pronounce.py`, appelé en fin de `normalize_for_speech` (`src/steph/tts.py`).
Tests : `tests/test_pronounce.py`.

## Résultat

| Voix | Rôle | Avant | Après | Avant (collages tolérés) | Après (collages tolérés) |
|---|---|---|---|---|---|
| Piper fr_FR-siwis-medium | référence de la boucle | 45/94 | **68/94** | 50/94 | **75/94** |
| macOS `say -v Thomas` | contrôle croisé | 64/94 | **76/94** | 67/94 | **80/94** |

- 94 mots cibles répartis sur 35 phrases réalistes (lignes `lspci`, messages git, apt, dmesg), dont 5 phrases françaises de contrôle.
- **Aucun mot français de contrôle n'est dégradé** : « commissions », « change », « la rate », « un clone célèbre », « son pull », « raté », `1.2.3`, `192.0.2.16`.
- Colonne « collages tolérés » : Whisper écrit parfois deux mots collés (`GitClone`, `LightHRAT`, `XHCIHCD`). Le score strict les compte faux ; le score toléré accepte un mot cible en début ou fin de mot collé.

## Méthode

- Aller-retour : texte envoyé à la voix, WAV, transcription Whisper large-v3-turbo (int8, `beam_size=5`, `condition_on_previous_text=False`), puis recherche de chaque mot cible dans la transcription.
- Boucle par mot : 3 à 6 graphies dans une phrase porteuse, sur siwis-medium, 5 tours au plus. Les graphies à égalité ont été répétées 3 fois : Piper tire un bruit aléatoire à chaque synthèse, un même texte peut passer puis échouer.
- Le texte « avant » est la sortie de `normalize_for_speech` sans `pronounce` ; « après » l'inclut.
- Whisper est un **proxy** : il mesure si un mot est reconnaissable, pas s'il sonne naturel. L'écoute humaine reste la décision.
- Scripts et données brutes : scratchpad de session `voicebench/pron/` (`rt.py`, `cand.py`, `sentences.py`, `report.py`), non versionnés.

## Règles de `pronounce`

| Table | Effet | Exemple |
|---|---|---|
| `SPOKEN` | graphie phonétique, toute casse | `git` : « guite », `dmesg` : « D M E S G » |
| `CAPS_ONLY` | graphie seulement en capitales | `BIOS` : « baïosse », « légumes bios » intact |
| `AMBIGUOUS` | graphie seulement à côté d'un mot technique | `git pull` : « guite pulle », « son pull » intact |
| `SPELLED` | épellation lettre par lettre | `xHCI` : « X H C I » |
| `KEEP` | sigle déjà bien lu, laissé tel quel | `USB`, `RTX`, `VGA`, `SATA` écrit `sata` |
| sigle inconnu | 2 à 3 capitales, ou sans voyelle jusqu'à 6 : épelé | `EIO` : « E I O », `EACCES` intact |
| nom de modèle | lettres et chiffres séparés | `GA106` : « G A 106 », `AX210` : « A X 210 » |
| protégé | mot collé à `.` ou `:` jamais touché | `2b:00.0`, `script.sh`, `1.2.3` |

Un mot absent des tables reste tel quel. C'est voulu : `sudo`, `push`, `build`, `driver`, `install`, `request`, `nginx`, `Ryzen`, `NVIDIA` passent déjà.

## Tableau par mot

Colonnes Whisper : mot reconnu / occurrences dans les 35 phrases (score strict). « Boucle » : meilleur score de la graphie retenue dans les phrases porteuses sur siwis.

| Mot | Avant (texte envoyé) | Graphie retenue | Boucle siwis | siwis avant | siwis après | Thomas avant | Thomas après | Statut |
|---|---|---|---|---|---|---|---|---|
| XHCI | `xHCI` | X H C I | 1/1 | 0/2 | 1/2 | 0/2 | 0/2 | amélioré siwis ; Thomas écrit « XHC » |
| lspci | `lspci` | L S, P C I | 2/2 | 0/1 | 0/1 | 0/1 | 1/1 | amélioré en boucle, Whisper écrit « LS, PCI » |
| PCI | `PCI` | P C I, (virgule = pause) | 4/4 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| AMD | `AMD` | A M D | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | inchangé, déjà bon |
| RTX | `RTX` | RTX (tel quel) | 1/1 | 0/1 | 0/1 | 1/1 | 1/1 | épeler dégrade siwis ; siwis entend « Vertex » dans la ligne lspci |
| Lite | `Lite` | laïte | 3/5 | 1/1 | 0/1 | 0/1 | 0/1 | **divergent** : meilleur en boucle, pire dans la ligne lspci ; Thomas écrit « Light » collé |
| Hash | `hash` | ache | 2/4 | 0/2 | 0/2 | 0/2 | 0/2 | **bloqué** : Whisper écrit « H » ou « âge » |
| Rate | `Rate` | Rate (tel quel) | 1/3 | 1/3 | 2/3 | 1/3 | 2/3 | **bloqué** en graphie ; « réte », « raite » pires |
| git | `git` | guite | 1/1 | 0/2 | 0/2 | 0/2 | 0/2 | **bloqué** : Whisper écrit « guide » ou « GitClone » collé |
| clone | `clone` | clone (tel quel) | 3/4 | 2/2 | 1/2 | 1/2 | 2/2 | inchangé ; l'échec siwis est « GitClone » collé |
| lsusb | `lsusb` | L S U S B | 2/2 | 0/1 | 1/1 | 0/1 | 1/1 | amélioré |
| lsblk | `lsblk` | L S B L K | 1/1 | 0/1 | 0/1 | 1/1 | 1/1 | siwis écrit « LSBL Cam » |
| dmesg | `dmesg` | D M E S G | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | Whisper écrit « DMSG » dans la phrase complète |
| sudo | `sudo` | sudo (tel quel) | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | déjà bon ; « soudou » dégrade |
| apt | `apt` | A P T | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| npm | `npm` | N P M | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| pnpm | `pnpm` | P N P M | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| ssh | `ssh` | S S H | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| chmod | `chmod` | C H mod | 3/5 | 0/1 | 0/1 | 0/1 | 0/1 | **bloqué** dans la phrase réelle : « C-H-MODE » |
| grep | `grep` | grep (tel quel) | 0/17 | 0/1 | 0/1 | 0/1 | 0/1 | **bloqué** : 12 graphies, Whisper écrit « greppe », phonétiquement juste |
| systemctl | `systemctl` | système C T L | 2/2 | 0/1 | 1/1 | 0/1 | 1/1 | amélioré, Whisper écrit « système CTL » |
| push | `push` | push (tel quel) | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | déjà bon |
| pull | `pull` | pulle (contexte technique) | 2/2 | 1/3 | 2/3 | 1/3 | 2/3 | amélioré ; « son pull » français intact |
| commit | `commit` | commite | 1/1 | 0/2 | 0/2 | 0/2 | 1/2 | partiel : Whisper écrit « commits » ou « comité » |
| build | `build` | build (tel quel) | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | déjà bon |
| kernel | `kernel` | keurnel | 1/1 | 1/2 | 2/2 | 2/2 | 2/2 | amélioré |
| firmware | `firmware` | feurmouère | 1/1 | 0/2 | 2/2 | 2/2 | 2/2 | amélioré |
| driver | `driver` | driver (tel quel) | 1/1 | 2/2 | 2/2 | 2/2 | 2/2 | déjà bon |
| USB | `USB` | USB (tel quel) | 1/1 | 2/2 | 2/2 | 2/2 | 2/2 | déjà bon ; épeler dégrade (« UTSB ») |
| NVMe | `NVMe` | N V M E | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| SATA | `SATA` | sata (minuscules) | 1/1 | 2/2 | 1/2 | 2/2 | 2/2 | capitales entendues « Seta » en boucle ; l'échec siwis est « SATAR-HC » collé |
| GPU | `GPU` | G, P, U | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| CPU | `CPU` | C P U | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| VGA | `VGA` | VGA (tel quel) | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | déjà bon en boucle |
| HDMI | `HDMI` | H D M I | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| SSD | `SSD` | S S D | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| RAM | `RAM` | R A M | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré ; « rame » donne le mot français |
| VRAM | `VRAM` | VRAM (tel quel) | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | déjà bon |
| PCH | `PCH` | pé cé ache | 1/1 | 0/1 | 0/1 | 1/1 | 1/1 | siwis écrit « PCHUSB » collé |
| ACPI | `ACPI` | ACPI (tel quel) | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | déjà bon ; épeler dégrade |
| AHCI | `AHCI` | A H C I | non testé | 0/1 | 0/1 | 0/1 | 0/1 | **bloqué** : « HCI » |
| PCIe | `PCIe` | P C I express | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 | **bloqué** sur siwis : « PC e-Express » |
| DRM | `DRM` | D R M | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| BIOS | `BIOS` | baïosse | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| GitHub | `GitHub` | guite hub | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | amélioré |
| GeForce | `GeForce` | gé force | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | bloqué en boucle (« G force »), bon en phrase |
| controller | `controller` | contrôleur | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | amélioré (traduit) |
| limit | `limit` | limite | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | **bloqué** : Whisper écrit « limite », juste à l'oreille |
| mount | `mount` | mount (tel quel) | 1/1 (« maount ») | 1/1 | 0/1 | 0/1 | 0/1 | non concluant : « maount » retiré, 0/1 sur siwis au retour du texte d'origine (bruit Piper) |
| GA106, AX210 | `GA106`, `AX210` | G A 106, A X 210 | non testé | 0/2 | 2/2 | 1/2 | 2/2 | amélioré |

## Divergences siwis / Thomas

- **Aucune graphie retenue ne dégrade Thomas** au score strict, hors `hcd` : Thomas lit juste mais Whisper colle « XHCIHCD ». Score toléré : 1/1 avant et après.
- **Lite** : la seule divergence réelle. « laïte » gagne dans les phrases porteuses (3/5 contre 0/5 pour `Lite`) mais perd dans la ligne `lspci` complète sur siwis. À trancher à l'écoute.
- `RTX`, `lsblk`, `PCH`, `nginx`, `sda1` : bons sur Thomas, faux sur siwis, avant comme après. Le défaut vient de la voix siwis, pas du texte.

## Écoute

- `docs/voice-bench/pron-siwis/` : 35 MP3 du texte corrigé, voix siwis-medium, `1.mp3` à `35.mp3` dans l'ordre des phrases ci-dessous.
- `docs/voice-bench/pron-thomas/` : les mêmes, voix Thomas.

| n | Phrase |
|---|---|
| 1 | 2b:00.0 VGA compatible controller: NVIDIA Corporation GA106 [GeForce RTX 3060 Lite Hash Rate] |
| 2 | 00:14.0 USB controller: Intel Corporation Alder Lake PCH USB 3.2 xHCI Host Controller |
| 3 | Lancez lspci pour lister les périphériques PCI. |
| 4 | git clone a échoué : dépôt introuvable. |
| 5 | Processeur AMD Ryzen 7 5800X détecté. |
| 6 | lsusb : 4 périphériques USB trouvés. |
| 7 | lsblk montre un SSD NVMe et un disque SATA. |
| 8 | dmesg signale une erreur du driver xhci_hcd. |
| 9 | Relancez avec sudo apt install firmware-misc-nonfree. |
| 10 | npm install a terminé, pnpm est plus rapide. |
| 11 | Connexion ssh refusée sur le port 22. |
| 12 | chmod +x script.sh puis relancez. |
| 13 | grep ne trouve rien dans le fichier. |
| 14 | systemctl restart nginx a réussi. |
| 15 | git push rejeté, faites d'abord un git pull. |
| 16 | Nouveau commit créé sur la branche principale. |
| 17 | Le build a échoué à cause du kernel 6.8. |
| 18 | Mise à jour du firmware du GPU terminée. |
| 19 | La carte graphique a 12 Go de VRAM, le CPU dispose de 16 Go de RAM. |
| 20 | Sortie HDMI détectée sur la carte NVIDIA. |
| 21 | Le hash du commit est 3f9a2c1. |
| 22 | Erreur ACPI du BIOS au démarrage. |
| 23 | Le périphérique PCIe tourne en x16. |
| 24 | Carte Wi-Fi Intel AX210 détectée. |
| 25 | Le module nvidia-drm est chargé par le kernel. |
| 26 | Téléchargement de CUDA 12.4 en cours. |
| 27 | Pull request fusionnée sur GitHub. |
| 28 | Montez le disque avec sudo mount /dev/sda1. |
| 29 | Le driver NVIDIA 550 est installé, rate limit atteint. |
| 30 | Contrôleur SATA AHCI en mode RAID. |
| 31 | Les commissions sont versées au taux de change. |
| 32 | La rate est un organe situé sous les côtes. |
| 33 | La brebis Dolly était un clone célèbre. |
| 34 | Version 1.2.3 installée sur 192.0.2.16. |
| 35 | Il a mis son pull et il a raté le train. |

## Non vérifié

- **Mots français de 3 lettres en capitales** hors de la liste `FRENCH_CAPS` : `NOM`, `BON`, `MOI` sont épelés. Limite connue de la règle générique des sigles.
- **Écoute humaine** : aucun MP3 n'a été écouté. Tout repose sur Whisper.
- **Bruit de Piper** : une seule synthèse par phrase à l'évaluation finale. Un écart de ±1 sur un mot isolé n'est pas significatif (`mount` perd 1 point avec un texte identique).
- Autres voix Piper (upmc, tom) et moteurs Linux (`spd-say`, `espeak-ng`) : non testés.
- `AHCI`, `GA106`, `AX210` et la règle générique des sigles inconnus : pas de boucle dédiée, seulement l'évaluation finale.
- Chemin initial `/dev/sda1` : le premier `/` reste avalé par `normalize_for_speech` (défaut n° 5 de `docs/voice-bench.md`), hors périmètre.

## Étape anglaise : tous les mots anglais, pas seulement ceux du lexique

`to_piper()` (dans `pronounce.py`) passe après le lexique, juste avant la synthèse Piper.
Elle n'est jamais appliquée à la voix système, qui lirait les crochets.

| Étape | Règle |
|---|---|
| Détection | mot de `data/english_words.txt.gz` (164 157 mots, wordfreq) ; identifiant camelCase toujours anglais |
| Mot aussi français (448 : rate, file, script) | anglais seulement si un indice technique est à 3 mots ou moins : sigle, chiffre, autre mot anglais, mot du lexique |
| Abréviation minuscule sans voyelle (pwd, ls) | épelée en lettres françaises |
| Phonèmes | espeak-ng `en-us`, puis 14 sons que la voix française n'a pas appris ramenés au plus proche (ɹ→ʁ, ʌ→œ, θ→s, aɪ→aj…) ; passés à Piper en `[[ ... ]]` |
| Panne (liste ou espeak absents) | texte rendu intact, la voix garde l'accent français |

Mesure : aller-retour Whisper `large-v3` sur une RTX 3060, 25 phrases, 5 répétitions
(la synthèse Piper est aléatoire : une seule passe ne permet pas de conclure).

| Variante | Mots reconnus |
|---|---|
| Lexique seul | 247/350 (71 %) |
| Lexique + étape anglaise `en-us` | 265/350 (76 %) |
| Lexique + étape anglaise `en` (britannique), boucle 1 | 146/210 (70 %), écarté |

Gains nets : curl 0→5, react 0→5, thread 0→4, lite 0→3, geforce 2→5. `sudo` et `push`, mieux
entendus à la française, sont dans `KEEP`. Toujours faibles : nginx, mount. Écoute : `docs/voice-bench/pronunciation-en/`.
Régénérer la liste : `scripts/build_english_words.py` (sources et licence CC BY-SA 4.0 : voir `NOTICE`).
