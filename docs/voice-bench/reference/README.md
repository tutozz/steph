# Banc de référence : LLM et voix par niveau de matériel, CPU seul

Mesuré le 2026-09-26 sur un serveur CPU (AMD Ryzen 5 5600, Zen 3, AVX2, sans AVX-512 ni VNNI).
Chaque niveau est simulé par un scope cgroup temporaire (`systemd-run --scope`, `AllowedCPUs`,
`CPUQuota`, `MemoryMax`), en priorité basse. La grille exploitable par `steph setup` est
`options.json`.

## Niveaux simulés

| Niveau | Cœurs | Plafond | RAM | Machine imitée |
|---|---|---|---|---|
| N1 | 1 physique + SMT | 100 % | 4 Go | vieux portable |
| N2 | 2 physiques | aucun | 4 Go | entrée de gamme |
| N3 | 4 physiques | aucun | 8 Go | bureau courant |
| N4 | 6 physiques | aucun | 7 Go | PC récent |

## LLM : temps avant le premier mot (médiane, 8 fixtures réelles)

| Modèle | N1 | N2 | N3 | N4 | RAM |
|---|---|---|---|---|---|
| Qwen3.5 0.8B | 6,2 s (1) | **1,9 s** | 1,1 s | 0,9 s | 1,4 Go |
| Qwen3.5 2B | hors de portée | 4,3 s | **2,4 s** | 1,8 s | 2,4 Go |
| Gemma 4 E2B | hors de portée | 6,2 s (1) | **3,4 s** (2) | **2,8 s** | 4,6 Go |
| Qwen3.5 4B | hors de portée | hors de portée | hors de portée (3) | 4,6 s | 5,6 Go |

1. Avec `summary_chars` à 1500, valeur par défaut actuelle de steph.
2. Médiane de 1,8 s sur les 29 fixtures ; les 8 retenues ici sont les plus lourdes.
3. Coupé après les 2 fixtures les plus lourdes (18 s) : à remesurer sur la série complète.

La vitesse de génération ne dépend presque pas du nombre de cœurs au-delà de N2 (Gemma : 10 mots/s
de N2 à N4) : elle est limitée par la bande passante mémoire. Le nombre de cœurs agit surtout
sur la lecture du prompt, donc sur le temps avant le premier mot.

## Qualité (faits vérifiables des fixtures)

| Modèle | docker ps (9 conteneurs) | apt upgrade (12 paquets) | npm run build |
|---|---|---|---|
| Qwen3.5 0.8B | « 10 », faux | juste | juste |
| Qwen3.5 2B | « 10 », faux | juste | juste, avec le fichier |
| Gemma 4 E2B | « cinq », faux | liste les paquets | mot pour mot la référence |
| Qwen3.5 4B | « huit », faux | « dix-huit », faux | le plus détaillé |

Aucun modèle ne compte juste. Ce jugement repose sur 5 fixtures : un score sur les 29, par un
juge humain ou un LLM plus gros, reste à faire.

## Voix : facteur temps réel (médiane) et premier son de la phrase la plus longue

| Voix | N1 | N2 | N3 | N4 | RAM |
|---|---|---|---|---|---|
| Piper siwis medium (défaut) | 0,40 · 0,64 s | 0,10 · 0,25 s | 0,03 · 0,07 s | 0,04 · 0,08 s | 240 Mo |
| Piper siwis low | 0,26 · 0,59 s | 0,05 · 0,13 s | 0,02 · 0,05 s | 0,02 · 0,04 s | 190 Mo |
| Piper upmc medium | 0,43 · 0,83 s | 0,09 · 0,22 s | 0,04 · 0,07 s | 0,04 · 0,07 s | 270 Mo |
| Piper mls medium | 0,38 · 1,27 s | 0,09 · 0,27 s | 0,04 · 0,09 s | 0,03 · 0,08 s | 280 Mo |
| Piper gilles low | 0,33 · 0,79 s | 0,07 · 0,14 s | 0,03 · 0,06 s | 0,02 · 0,05 s | 240 Mo |
| Piper mls_1840 low | 0,23 · 1,41 s | 0,06 · 0,35 s | 0,03 · 0,11 s | 0,02 · 0,16 s | 350 Mo |
| Piper tom medium | 0,70 · 1,78 s (limite) | 0,16 · 0,41 s | 0,07 · 0,17 s | 0,06 · 0,13 s | 395 Mo |
| Kokoro-82M fp32 | hors de portée | 0,40 · 3,23 s | 0,27 · 2,28 s | 0,24 · 1,98 s | 630 Mo |
| Kokoro-82M int8 | hors de portée | hors de portée | hors de portée | hors de portée | 390 Mo |

Au-dessus d'un facteur temps réel de 1, la voix bégaie. Kokoro synthétise la phrase entière avant
de parler : son premier son arrive 2 à 3 s plus tard que Piper. Son int8 est plus lent que son fp32
sur un CPU sans VNNI. L'intelligibilité se juge à l'écoute : `samples/`, même phrase pour chaque voix.

## OpenVINO contre llama.cpp

Même modèle (Qwen3-1.7B, Q4_K_M contre int4 OpenVINO), qualité équivalente :

| Niveau | llama.cpp | OpenVINO |
|---|---|---|
| N2 | 4,1 s · 13,2 mots/s | 4,7 s · 11,6 mots/s |
| N3 | 2,3 s · 13,8 mots/s | 2,6 s · 12,3 mots/s |

OpenVINO est 13 à 15 % plus lent sur ce CPU AMD. Il reste à mesurer là où il est optimisé :
CPU Intel avec VNNI ou AMX, iGPU Arc, NPU.

## Limites

- Un seul CPU réel (Zen 3). Un vieux Celeron double cœur est plus lent par cœur que le N2 simulé :
  les seuils en nombre de cœurs sont indicatifs. Une mesure de calibrage de quelques secondes
  pendant `steph setup` classerait la machine plus sûrement.
- Les seuils GPU (VRAM) sont déduits du README (T600 4 Go) et de la taille des modèles, pas mesurés ici.
- Qualité jugée sur 5 fixtures seulement.

## Fichiers

- `options.json` : grille, une entrée par option, seuils et mesures.
- `llm/`, `tts/` : mesures brutes par combinaison.
- `samples/` : une phrase par voix, MP3.
- `scripts/` : bancs et pilotes utilisés sur ce serveur.
