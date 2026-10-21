# Pronunciation of acronyms, commands and English words

[Français](pronunciation.fr.md)

Measured on 2026-09-26 and 2026-09-27 on a MacBook Pro M3 Pro, CPU only.
Code: `src/steph/pronounce.py`, called at the end of `normalize_for_speech` (`src/steph/tts.py`).
Tests: `tests/test_pronounce.py`.

steph speaks French today (see the [main README](../README.md)), so every rule below rewrites
text for the French Piper voice. The test sentences and the French control words are kept in
French throughout this page: translating them would misrepresent the actual audio files and the
point being tested.

## Result

| Voice | Role | Before | After | Before (merged words tolerated) | After (merged words tolerated) |
|---|---|---|---|---|---|
| Piper fr_FR-siwis-medium | loop reference | 45/94 | **68/94** | 50/94 | **75/94** |
| macOS `say -v Thomas` | cross-check | 64/94 | **76/94** | 67/94 | **80/94** |

- 94 target words spread across 35 realistic sentences (`lspci` lines, git messages, apt, dmesg
  output), including 5 French control sentences.
- **No French control word gets worse**: "commissions", "change", "la rate" (the spleen), "un
  clone célèbre" (a famous clone), "son pull" (his sweater), "raté" (missed/failed), `1.2.3`,
  `192.0.2.16`.
- "Merged words tolerated" column: Whisper sometimes writes two words stuck together
  (`GitClone`, `LightHRAT`, `XHCIHCD`). The strict score counts these as wrong; the tolerant
  score accepts a target word at the start or end of a merged word.

## Method

- Round trip: text sent to the voice, WAV file, Whisper large-v3-turbo transcription (int8,
  `beam_size=5`, `condition_on_previous_text=False`), then each target word is searched for in
  the transcript.
- Per-word loop: 3 to 6 spellings tried in a carrier sentence, on siwis-medium, 5 rounds at
  most. Tied spellings were repeated 3 times: Piper draws random noise on every synthesis, so
  the same text can pass once and fail the next time.
- The "before" text is the output of `normalize_for_speech` without `pronounce`; "after"
  includes it.
- Whisper is a **proxy**: it measures whether a word is recognizable, not whether it sounds
  natural. Human listening is still the final call.
- Scripts and raw data: session scratchpad `voicebench/pron/` (`rt.py`, `cand.py`,
  `sentences.py`, `report.py`), not version-controlled.

## `pronounce` rules

| Table | Effect | Example |
|---|---|---|
| `SPOKEN` | phonetic spelling, any case | `git`: "guite" (a French phonetic respelling), `dmesg`: "D M E S G" |
| `CAPS_ONLY` | the spelling only applies in capitals | `BIOS`: "baïosse"; the French phrase "légumes bios" (organic vegetables) stays intact |
| `AMBIGUOUS` | the spelling only applies next to a technical word | `git pull`: "guite pulle"; the French phrase "son pull" (his sweater) stays intact |
| `SPELLED` | spelled out letter by letter | `xHCI`: "X H C I" |
| `KEEP` | acronym already read correctly, left as is | `USB`, `RTX`, `VGA`, `SATA` written `sata` |
| unknown acronym | 2 to 3 capitals, or no vowel up to 6 letters: spelled out | `EIO`: "E I O", `EACCES` stays intact |
| model name | letters and digits split apart | `GA106`: "G A 106", `AX210`: "A X 210" |
| protected | a word glued to `.` or `:` is never touched | `2b:00.0`, `script.sh`, `1.2.3` |

A word absent from the tables stays as is. That is intentional: `sudo`, `push`, `build`,
`driver`, `install`, `request`, `nginx`, `Ryzen`, `NVIDIA` already come through fine.

## Per-word table

Whisper columns: word recognized / occurrences across the 35 sentences (strict score). "Loop":
best score of the chosen spelling across the carrier sentences on siwis.

| Word | Before (text sent) | Spelling used | siwis loop | siwis before | siwis after | Thomas before | Thomas after | Status |
|---|---|---|---|---|---|---|---|---|
| XHCI | `xHCI` | X H C I | 1/1 | 0/2 | 1/2 | 0/2 | 0/2 | improved on siwis; Thomas writes "XHC" |
| lspci | `lspci` | L S, P C I | 2/2 | 0/1 | 0/1 | 0/1 | 1/1 | improved in the loop, Whisper writes "LS, PCI" |
| PCI | `PCI` | P C I, (comma = pause) | 4/4 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| AMD | `AMD` | A M D | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | unchanged, already good |
| RTX | `RTX` | RTX (as is) | 1/1 | 0/1 | 0/1 | 1/1 | 1/1 | spelling it out degrades siwis; siwis hears "Vertex" in the lspci line |
| Lite | `Lite` | laïte | 3/5 | 1/1 | 0/1 | 0/1 | 0/1 | **diverging**: better in the loop, worse in the full lspci line; Thomas writes a merged "Light" |
| Hash | `hash` | ache | 2/4 | 0/2 | 0/2 | 0/2 | 0/2 | **stuck**: Whisper writes "H" or the French word "âge" (age) |
| Rate | `Rate` | Rate (as is) | 1/3 | 1/3 | 2/3 | 1/3 | 2/3 | **stuck** on spelling; "réte", "raite" are worse |
| git | `git` | guite | 1/1 | 0/2 | 0/2 | 0/2 | 0/2 | **stuck**: Whisper writes "guide" or a merged "GitClone" |
| clone | `clone` | clone (as is) | 3/4 | 2/2 | 1/2 | 1/2 | 2/2 | unchanged; the siwis failure is a merged "GitClone" |
| lsusb | `lsusb` | L S U S B | 2/2 | 0/1 | 1/1 | 0/1 | 1/1 | improved |
| lsblk | `lsblk` | L S B L K | 1/1 | 0/1 | 0/1 | 1/1 | 1/1 | siwis writes "LSBL Cam" |
| dmesg | `dmesg` | D M E S G | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | Whisper writes "DMSG" in the full sentence |
| sudo | `sudo` | sudo (as is) | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | already good; "soudou" makes it worse |
| apt | `apt` | A P T | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| npm | `npm` | N P M | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| pnpm | `pnpm` | P N P M | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| ssh | `ssh` | S S H | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| chmod | `chmod` | C H mod | 3/5 | 0/1 | 0/1 | 0/1 | 0/1 | **stuck** in the real sentence: "C-H-MODE" |
| grep | `grep` | grep (as is) | 0/17 | 0/1 | 0/1 | 0/1 | 0/1 | **stuck**: 12 spellings tried, Whisper writes "greppe", which is phonetically correct anyway |
| systemctl | `systemctl` | système C T L | 2/2 | 0/1 | 1/1 | 0/1 | 1/1 | improved, Whisper writes "système CTL" |
| push | `push` | push (as is) | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | already good |
| pull | `pull` | pulle (technical context) | 2/2 | 1/3 | 2/3 | 1/3 | 2/3 | improved; the French phrase "son pull" stays intact |
| commit | `commit` | commite | 1/1 | 0/2 | 0/2 | 0/2 | 1/2 | partial: Whisper writes "commits" or "comité" |
| build | `build` | build (as is) | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | already good |
| kernel | `kernel` | keurnel | 1/1 | 1/2 | 2/2 | 2/2 | 2/2 | improved |
| firmware | `firmware` | feurmouère | 1/1 | 0/2 | 2/2 | 2/2 | 2/2 | improved |
| driver | `driver` | driver (as is) | 1/1 | 2/2 | 2/2 | 2/2 | 2/2 | already good |
| USB | `USB` | USB (as is) | 1/1 | 2/2 | 2/2 | 2/2 | 2/2 | already good; spelling it out makes it worse ("UTSB") |
| NVMe | `NVMe` | N V M E | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| SATA | `SATA` | sata (lowercase) | 1/1 | 2/2 | 1/2 | 2/2 | 2/2 | capitals heard as "Seta" in the loop; the siwis failure is a merged "SATAR-HC" |
| GPU | `GPU` | G, P, U | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| CPU | `CPU` | C P U | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| VGA | `VGA` | VGA (as is) | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | already good in the loop |
| HDMI | `HDMI` | H D M I | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| SSD | `SSD` | S S D | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| RAM | `RAM` | R A M | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved; "rame" gives back the French word (subway train) |
| VRAM | `VRAM` | VRAM (as is) | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | already good |
| PCH | `PCH` | pé cé ache | 1/1 | 0/1 | 0/1 | 1/1 | 1/1 | siwis writes a merged "PCHUSB" |
| ACPI | `ACPI` | ACPI (as is) | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | already good; spelling it out makes it worse |
| AHCI | `AHCI` | A H C I | not tested | 0/1 | 0/1 | 0/1 | 0/1 | **stuck**: "HCI" |
| PCIe | `PCIe` | P C I express | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 | **stuck** on siwis: "PC e-Express" |
| DRM | `DRM` | D R M | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| BIOS | `BIOS` | baïosse | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| GitHub | `GitHub` | guite hub | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | improved |
| GeForce | `GeForce` | gé force | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | stuck in the loop ("G force"), good in the full sentence |
| controller | `controller` | contrôleur | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | improved (translated) |
| limit | `limit` | limite | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | **stuck**: Whisper writes "limite", which is correct to the ear anyway |
| mount | `mount` | mount (as is) | 1/1 ("maount") | 1/1 | 0/1 | 0/1 | 0/1 | inconclusive: "maount" was dropped, 0/1 on siwis when reverting to the original text (Piper noise) |
| GA106, AX210 | `GA106`, `AX210` | G A 106, A X 210 | not tested | 0/2 | 2/2 | 1/2 | 2/2 | improved |

## siwis / Thomas divergences

- **No chosen spelling makes Thomas worse** on the strict score, except `hcd`: Thomas reads it
  correctly but Whisper merges it into "XHCIHCD". Tolerant score: 1/1 before and after.
- **Lite**: the only real divergence. "laïte" wins in the carrier sentences (3/5 against 0/5 for
  `Lite`) but loses in the full `lspci` line on siwis. To be settled by ear.
- `RTX`, `lsblk`, `PCH`, `nginx`, `sda1`: correct on Thomas, wrong on siwis, both before and
  after. The gap comes from the siwis voice, not the text.

## Recordings

- `docs/voice-bench/pron-siwis/`: 35 MP3 files of the corrected text, siwis-medium voice,
  `1.mp3` to `35.mp3` in the order of the sentences below.
- `docs/voice-bench/pron-thomas/`: the same, Thomas voice.

The sentences are the literal French text sent to the voice: steph speaks French only for now,
so they are kept as spoken, not translated.

| n | Sentence |
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

## Not verified

- **Three-letter French words in capitals** outside the `FRENCH_CAPS` list: `NOM`, `BON`, `MOI`
  get spelled out letter by letter. A known limit of the generic acronym rule.
- **Human listening**: no MP3 was actually listened to. Everything here relies on Whisper.
- **Piper noise**: a single synthesis per sentence at the final evaluation. A ±1 gap on a single
  word is not significant (`mount` loses 1 point with identical text).
- Other Piper voices (upmc, tom) and Linux engines (`spd-say`, `espeak-ng`): not tested.
- `AHCI`, `GA106`, `AX210` and the generic rule for unknown acronyms: no dedicated loop, only
  the final evaluation.
- Initial path `/dev/sda1`: the leading `/` is still swallowed by `normalize_for_speech`
  (defect #5 of `docs/voice-bench.md`), out of scope here.

## English step: every English word, not just the lexicon

`to_piper()` (in `pronounce.py`) runs after the lexicon, just before Piper synthesis. It is
never applied to the system voice, which would read the brackets aloud.

| Step | Rule |
|---|---|
| Detection | a word from `data/english_words.txt.gz` (164,157 words, wordfreq); a camelCase identifier is always treated as English |
| Word that is also French (448 words: rate, file, script) | treated as English only if a technical clue sits within 3 words: an acronym, a digit, another English word, a lexicon word |
| Lowercase abbreviation with no vowel (pwd, ls) | spelled out in French letters |
| Phonemes | espeak-ng `en-us`, then 14 sounds the French voice never learned are mapped to the closest one (ɹ→ʁ, ʌ→œ, θ→s, aɪ→aj…); passed to Piper as `[[ ... ]]` |
| Failure (list or espeak missing) | text passed through unchanged, the voice keeps its French accent |

Measurement: Whisper `large-v3` round trip on an RTX 3060, 25 sentences, 5 repeats (Piper
synthesis is random: a single pass is not conclusive).

| Variant | Words recognized |
|---|---|
| Lexicon only | 247/350 (71%) |
| Lexicon + English step `en-us` | 265/350 (76%) |
| Lexicon + English step `en` (British), loop 1 | 146/210 (70%), dropped |

Net gains: curl 0→5, react 0→5, thread 0→4, lite 0→3, geforce 2→5. `sudo` and `push`, better
recognized with a French pronunciation, are in `KEEP`. Still weak: nginx, mount. Recordings:
`docs/voice-bench/pronunciation-en/`.
Regenerate the list: `scripts/build_english_words.py` (sources and CC BY-SA 4.0 license: see
`NOTICE`).
