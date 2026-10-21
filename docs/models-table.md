# Tableau de fin de round : tous les modèles testés

Généré par `bench/matrix/models_table.py`, jamais retapé à la main. Relancer après tout
nouveau résultat dans `bench/matrix/results/`.

## Légende

- **Protocole** : `steph long` (prompt système complet, bancs bruts des vagues 1 et 2, 69 cas) ;
  `court affiné` (prompt d'entraînement court, 36 cas, utilisé pour comparer les modèles affinés
  entre eux et contre leur base) ; `TermSpeak` (benchmark ouvert `benchmark/`). Les scores ne se
  comparent qu'à l'intérieur d'un même protocole.
- **Type** : `brut` (poids tels que publiés) ou `affiné` (LoRA maison sur le corpus de steph).
- **Données** : `brutes` (étiquettes non relues), `corrigées` (après P1, `facts.v2.json` et le
  nettoyage des étiquettes), `filtrées au juge` (après A11, rejet des étiquettes que le juge IA
  trouve inventées).
- **Total v2 / Contrôle v2 / Résumé seul v2** : score sur `facts.v2.json` (`rescore.py`) - total,
  jeu de contrôle (`score.HOLDOUT`, jamais utilisé pour choisir un réglage), et résumé seul
  (contrôle sans les questions). **Total v1** : même calcul avec `facts.json` (`score.py`), pour
  mesurer l'écart avant/après l'audit P1.
- **Inventions /36 (juge)** : cas confirmés par le juge IA (Qwen3.5 9B, 2 passes), après révision
  humaine dans `judge_audit.v2.json`. **+ resolve()** : inventions restantes une fois les 28 cas
  que `resolve()` dit en code (P4) retirés du calcul - seuls les cas encore envoyés au modèle
  peuvent inventer.
- Une graine de banc (`-b7/-b42/-b123` ou `-s7/-s42/-s123`) donne une moyenne et une fourchette
  `moyenne (min–max)`. Une ronde de mesure i5 (`-r2`, `-r3`) donne une médiane et une fourchette.
  Cellule vide = non mesuré, jamais estimé.

**Plancher retenu (A9) : au plus 1 invention sur 36, moins de 3 s au 90e centile sur l'i5-7200U.**
Les lignes en gras tiennent les deux à la fois.


| Modèle | Protocole | Type | Données | Variante | Taille GGUF (Mo) | Premier mot médian i5 (s) | Premier mot p90 i5 (s) | RAM i5 (Mo) | Total v2 | Contrôle v2 | Résumé seul v2 | Total v1 | Inventions /36 (juge) | + resolve() : inventions |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma 4 E2B | steph long | brut |  |  |  |  |  |  | 97,5 | 100,0 | 100,0 | 97,5 |  |  |
| Qwen3 4B Instruct 2507 | steph long | brut |  |  |  |  |  |  | 97,2 | 100,0 | 100,0 | 97,2 |  |  |
| Ministral 3 8B | steph long | brut |  |  |  |  |  |  | 93,3 | 93,3 | 100,0 | 91,9 |  |  |
| Granite 4.2 8B | steph long | brut |  |  |  |  |  |  | 86,4 | 86,7 | 83,3 | 96,1 |  |  |
| Qwen3.5 2B | steph long | brut |  |  |  | 3,3 | 13,3 | 2712 | 85,6 | 81,3 | 93,3 | 85,6 |  |  |
| Ministral 3 3B | steph long | brut |  |  |  | 5,1 | 27,0 | 5120 | 84,7 | 80,0 | 91,7 | 86,1 |  |  |
| Qwen3.5 9B | steph long | brut |  |  |  |  |  |  | 83,3 | 80,0 | 75,0 | 100,0 |  |  |
| Qwen3.5 4B | steph long | brut |  |  |  |  |  |  | 79,2 | 86,7 | 91,7 | 81,9 |  |  |
| Granite 4.2 3B | steph long | brut |  |  |  |  |  |  | 76,7 | 78,7 | 73,3 | 85,0 |  |  |
| Gemma 4 E4B | steph long | brut |  |  |  |  |  |  | 76,4 | 76,7 | 70,8 | 95,8 |  |  |
| Luth 0.6B | steph long | brut |  | avant réglage |  | 1,6 | 4,0 | 1896 | 71,9 | 67,9 | 79,2 | 59,4 |  |  |
| Qwen3.5 0.8B | steph long | brut |  |  |  | 1,5 | 5,7 | 1654 | 69,3 | 56,7 | 62,5 | 62,5 |  |  |
| SmolLM3 3B | steph long | brut |  |  |  | 5,1 | 22,4 | 4181 | 66,4 | 82,7 | 78,3 | 67,8 |  |  |
| Luth LFM2 350M | steph long | brut |  |  |  | 1,6 | 2,6 | 573 | 63,1 | 57,9 | 67,5 | 68,1 |  |  |
| Luth LFM2 350M | steph long | brut |  |  |  | 1,2 | 2,0 | 566 | 57,3 | 52,3 | 56,7 | 60,7 |  |  |
| Qwen3 0.6B | steph long | brut |  |  |  | 1,7 | 4,0 | 1904 | 53,3 | 46,2 | 50,0 | 46,7 |  |  |
| Luth LFM2 350M | steph long | brut |  |  |  | 0,8 | 4,4 | 581 | 52,5 | 48,6 | 56,7 | 58,8 |  |  |
| LFM2 700M | steph long | brut |  |  |  | 2,3 | 4,4 | 972 | 52,5 | 45,7 | 53,3 | 70,0 |  |  |
| LFM2.5 1.2B | steph long | brut |  |  |  | 4,4 | 9,7 | 1468 | 44,4 | 36,7 | 45,8 | 43,1 |  |  |
| Falcon H1 0.5B | steph long | brut |  |  |  | 1,6 | 4,4 | 978 | 42,5 | 37,1 | 30,0 | 32,5 |  |  |
| Qwen3.5 0.8B | steph long | brut |  | Q4_0 |  | 1,6 | 3,9 | 1142 | 38,3 | 28,8 | 31,2 | 38,3 |  |  |
| Qwen3 0.6B | steph long | brut |  |  |  | 1,6 | 4,0 | 1670 | 37,5 | 28,6 | 33,3 | 31,2 |  |  |
| Luth LFM2 700M | steph long | brut |  |  |  | 3,4 | 5,7 | 984 | 34,4 | 39,3 | 29,2 | 34,4 |  |  |
| LFM2.5 8B-A1B | steph long | brut |  |  |  |  |  |  | 31,4 | 49,3 | 36,7 | 31,4 |  |  |
| Granite 4.0 H 1B | steph long | brut |  |  |  | 5,6 | 9,9 | 2842 | 28,1 | 32,1 | 20,8 | 28,1 |  |  |
| LFM2.5 350M | steph long | brut |  |  |  | 0,7 | 4,5 | 578 | 28,0 | 23,9 | 21,5 | 28,5 |  |  |
| Falcon H1 0.5B | steph long | brut |  |  |  | 2,2 | 4,8 | 1716 | 26,0 | 23,8 | 19,2 | 26,0 |  |  |
| SmolLM2 360M | steph long | brut |  |  |  | 1,3 | 3,2 | 886 | 18,8 | 7,1 | 8,3 | 18,8 |  |  |
| LFM2.5 350M | steph long | brut |  |  |  | 1,2 | 2,0 | 560 | 16,7 | 19,2 | 20,8 | 16,7 |  |  |
| Granite 4.0 H 350M | steph long | brut |  |  |  | 0,7 | 1,7 | 631 | 14,7 | 12,0 | 15,0 | 13,3 |  |  |
| Gemma 3 270M | steph long | brut |  |  |  | 1,4 | 3,0 | 521 | 14,0 | 14,9 | 18,6 | 14,4 |  |  |
| Gemma 3 270M | steph long | brut |  |  |  | 0,7 | 1,4 | 499 | 12,0 | 0,0 | 0,0 | 12,0 |  |  |
| Granite 4.0 H 350M | steph long | brut |  |  |  | 1,2 | 2,4 | 922 | 3,3 | 3,8 | 4,2 | 3,3 |  |  |
| Qwen3.5 0.8B | court affiné | affiné | corrigées | corrigé (bug fx29), graine s42 | 542 |  |  |  | 86,8 | 85,0 | 89,6 | 88,2 | 2 | 1 |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | graine s42 | 223 | 0,6 | 2,3 | 2545 | 84,0 (80,6–86,2) | 78,5 (66,7–86,7) | 81,5 (66,7–91,7) | 78,0 (75,0–80,7) | 6 | 1 |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | soupe gloutonne | 223 | 0,6 | 2,5 | 2459 | 83,9 (81,9–86,9) | 76,7 (70,0–83,3) | 79,2 (70,8–87,5) | 75,5 (72,2–80,0) | 7 | 3 |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | meilleure graine seule (s42) | 223 | 0,6 | 2,5 | 2545 | 83,8 (77,2–89,2) | 76,8 (73,3–82,0) | 79,4 (75,0–85,8) | 78,6 (75,8–80,6) | 9 | 3 |
| Qwen3.5 0.8B | court affiné | affiné | corrigées | corrigé, graine entraînement s7 |  |  |  |  | 83,5 | 78,3 | 89,6 | 82,1 |  |  |
| Granite 4.0 H 350M | court affiné | affiné | corrigées | boucle opt G1-G19 (référence, meilleure itération) |  |  |  |  | 82,8 | 72,0 | 81,7 | 80,0 | 8 | 1 |
| i5-vocab-granite-c65536-Q4_K_M-p04 | court affiné | ? |  |  |  | 0,6 | 2,5 | 2534 | 82,5 | 76,0 | 78,3 | 81,1 |  |  |
| Gemma 3 270M | court affiné | affiné | filtrées au juge | vocabulaire réduit v20000 |  | 0,6 (0,5–0,6) | 1,7 (1,5–1,7) | 489 | 82,2 (80,6–85,4) | 67,0 (60,0–75,0) | 75,4 (66,7–85,4) | 79,0 (76,4–82,6) |  |  |
| Gemma 3 270M | court affiné | affiné | filtrées au juge | vocabulaire corpus c65536 |  | 0,5 | 1,7 (1,7–1,8) | 536 | 82,1 (77,5–87,3) | 67,1 (59,4–76,1) | 77,2 (66,0–86,8) | 81,4 (77,1–85,4) |  |  |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | meilleure graine seule (s42) | 366 |  |  |  | 81,9 | 67,8 (63,3–70,0) | 76,4 (70,8–79,2) | 82,9 (80,6–84,7) | 8 | 4 |
| i5-vocab-granite-b32768-Q4_K_M-p06 | court affiné | ? |  |  |  | 0,6 | 2,5 | 2397 | 81,7 | 79,3 | 82,5 | 76,1 |  |  |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | soupe gloutonne | 366 |  |  |  | 81,6 (77,9–84,9) | 67,0 (60,3–70,3) | 75,4 (67,1–79,6) | 78,4 (76,5–79,3) | 8 | 4 |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | soupe uniforme (4 graines) | 223 | 0,6 | 2,2 | 2545 | 81,5 (77,9–84,2) | 83,4 (81,0–85,3) | 87,6 (84,6–90,0) | 79,8 (77,6–81,4) | 7 | 1 |
| Gemma 3 270M | court affiné | affiné | filtrées au juge | vocabulaire réduit v32768 |  | 0,6 | 1,7 | 499 | 81,4 (77,9–84,0) | 65,9 (61,7–68,3) | 78,2 (68,8–85,4) | 78,6 (75,7–81,2) |  |  |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | graine s7 | 223 | 0,6 | 2,5 | 2457 | 80,7 (77,1–83,3) | 77,1 (66,7–85,0) | 79,7 (66,7–89,6) | 76,5 (72,9–81,9) | 14 | 3 |
| Gemma 3 270M | court affiné | affiné | filtrées au juge | graine s42 | 292 | 0,6 | 1,7 | 691 | 79,2 (75,1–82,6) | 64,2 (63,3–65,0) | 78,2 (72,9–81,2) | 76,8 (74,3–77,9) | 8 | 2 |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | graine s42 | 366 |  |  |  | 79,2 (77,8–81,9) | 58,9 (53,3–70,0) | 65,3 (58,3–79,2) | 80,1 (77,8–84,7) | 6 | 3 |
| i5-vocab-granite-full-Q4_K_M-p01 | court affiné | ? |  |  |  | 0,6 | 2,3 | 2546 | 79,0 | 81,0 | 84,6 | 77,6 |  |  |
| Gemma 3 270M | court affiné | affiné | filtrées au juge | vocabulaire plein (référence P2) | 366 | 0,5 (0,5–0,6) | 1,7 (1,6–1,7) | 690 | 78,9 (74,4–80,6) | 62,0 (60,0–66,7) | 73,4 (66,7–83,3) | 76,8 (75,0–77,8) |  |  |
| Gemma 3 270M | court affiné | affiné | filtrées au juge | vocabulaire corpus c131072 |  |  |  |  | 78,1 (77,1–79,3) | 61,9 (60,3–63,7) | 77,4 (75,4–79,6) | 77,2 (75,7–77,9) |  |  |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | soupe uniforme (4 graines) | 366 |  |  |  | 77,1 (75,7–78,5) | 60,6 (55,0–65,0) | 70,2 (68,8–72,9) | 76,2 (74,3–77,1) | 9 | 4 |
| Qwen3.5 0.8B | court affiné | affiné | corrigées | entraînement complet | 542 | 1,3 | 5,4 | 2802 | 77,1 | 65,0 | 72,9 | 91,0 | 6 | 1 |
| i5-vocab-granite-c32768-Q4_K_M-p02 | court affiné | ? |  |  |  | 0,7 | 2,5 | 2050 | 75,7 | 68,3 | 68,8 | 72,9 |  |  |
| Granite 4.0 H 350M | court affiné | affiné | corrigées | boucle opt G1-G19 (référence, meilleure itération) | 223 | 0,7 | 2,6 | 2545 | 75,0 | 70,0 | 70,8 | 86,1 | 8 | 2 |
| Luth 0.6B | court affiné | affiné | brutes | LoRA r16 | 397 |  |  |  | 75,0 | 63,3 | 70,8 | 86,1 |  |  |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | vocabulaire réduit b32768 (P2b) | 178 |  |  |  | 74,7 (72,4–78,6) | 74,8 (73,7–75,3) | 76,8 (75,4–77,5) | 75,6 (73,1–78,6) |  |  |
| flan-t5-small | court affiné | affiné | filtrées au juge | encodeur-décodeur (P3) | 155 |  |  |  | 74,7 (73,1–77,2) | 50,6 (46,7–56,7) | 60,4 (58,3–62,5) | 77,0 (75,8–78,6) |  |  |
| Gemma 3 270M | court affiné | affiné | filtrées au juge | vocabulaire plein (référence P2) | 223 | 0,6 | 1,9 | 666 | 74,5 (69,4–83,1) | 52,1 (46,7–68,3) | 65,1 (58,3–85,4) | 75,2 (69,4–84,0) |  |  |
| Gemma 3 270M | court affiné | affiné | filtrées au juge | vocabulaire corpus c65536 | 199 |  |  |  | 74,1 (72,9–76,5) | 64,5 (55,0–70,3) | 64,1 (52,1–71,3) | 74,1 (72,9–76,5) |  |  |
| flan-t5-small | court affiné | affiné | filtrées au juge | encodeur-décodeur (P3) | 155 | 0,4 | 0,8 |  | 73,8 | 48,3 | 60,4 | 76,5 |  |  |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | vocabulaire corpus c32768 (P2b) | 178 |  |  |  | 73,5 (71,7–75,8) | 63,1 (58,7–68,7) | 67,8 (56,7–77,5) | 74,5 (73,1–77,2) |  |  |
| flan-t5-small | court affiné | affiné | filtrées au juge | encodeur-décodeur (P3) | 83 |  |  |  | 73,2 (71,4–74,4) | 48,3 (46,7–50,0) | 60,4 (58,3–62,5) | 76,0 (74,2–77,2) |  |  |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | vocabulaire corpus c32768 (P2b) |  |  |  |  | 73,2 (68,5–76,2) | 54,4 (51,1–59,4) | 59,7 (55,6–66,0) | 69,4 (66,7–71,5) |  |  |
| flan-t5-base | court affiné | affiné | filtrées au juge | encodeur-décodeur (P3) | 264 |  |  |  | 73,0 (71,0–75,7) | 49,4 (45,0–55,0) | 61,8 (56,2–68,8) | 73,0 (71,0–75,7) |  |  |
| flan-t5-base | court affiné | affiné | filtrées au juge | encodeur-décodeur (P3) | 496 |  |  |  | 73,0 (71,0–75,7) | 49,4 (45,0–55,0) | 61,8 (56,2–68,8) | 73,0 (71,0–75,7) |  |  |
| Gemma 3 270M | court affiné | affiné | filtrées au juge | vocabulaire réduit v20000 |  | 0,6 | 1,9 | 466 | 72,9 (68,8–80,3) | 52,5 (48,3–65,0) | 65,6 (60,4–81,2) | 73,6 (68,8–81,2) |  |  |
| Luth 0.6B | court affiné | affiné | brutes | LoRA r16 | 397 | 0,9 | 4,6 | 2146 | 72,9 | 58,3 | 72,9 | 86,8 | 7 | 2 |
| Gemma 3 270M | court affiné | affiné | filtrées au juge | vocabulaire réduit v32768 |  | 0,6 | 1,9 | 481 | 72,6 (68,8–77,5) | 50,8 (48,3–58,3) | 63,5 (60,4–72,9) | 73,3 (68,8–78,5) |  |  |
| flan-t5-small | court affiné | affiné | filtrées au juge | encodeur-décodeur (P3) | 83 | 0,3 | 0,7 |  | 72,4 | 45,0 | 56,2 | 75,1 |  |  |
| Granite 4.0 H 350M | court affiné | affiné | filtrées au juge | graine s7 | 366 |  |  |  | 72,0 (68,1–77,1) | 55,0 (50,0–65,0) | 66,0 (62,5–72,9) | 71,1 (68,1–74,3) | 9 | 5 |
| Qwen3.5 0.8B | court affiné | affiné | corrigées | entraînement complet | 834 | 1,7 | 6,9 | 2844 | 71,5 | 65,0 | 72,9 | 89,6 | 7 | 0 |
| Luth 0.6B | court affiné | affiné | brutes | LoRA r32 | 397 |  |  |  | 70,8 | 56,7 | 62,5 | 81,9 |  |  |
| Granite 4.0 H 350M | court affiné | affiné | corrigées | boucle opt G4 (données brutes) |  |  |  |  | 69,6 | 57,0 | 62,9 | 84,9 |  |  |
| Granite 4.0 H 350M | court affiné | affiné | corrigées | boucle opt G1-G19 (référence, meilleure itération) | 366 |  |  |  | 69,6 | 65,0 | 64,6 | 83,5 |  |  |
| Gemma 3 270M | court affiné | affiné | corrigées | entraînement complet (avant filtrage juge) | 292 | 0,6 | 1,8 | 695 | 67,5 | 52,0 | 65,0 | 82,1 | 9 | 3 |
| Qwen3.5 0.8B | court affiné | affiné | brutes | LoRA pilote (A4p) | 542 |  |  |  | 66,8 | 48,3 | 52,1 | 84,9 |  |  |
| Granite 4.0 H 350M | court affiné | affiné | corrigées | boucle opt G1-G19 (référence, meilleure itération) | 366 | 0,9 | 3,2 | 2551 | 66,7 | 56,7 | 70,8 | 83,3 | 12 | 3 |
| Gemma 3 270M | court affiné | affiné | corrigées | entraînement complet (avant filtrage juge) | 253 |  |  |  | 63,9 | 40,0 | 50,0 | 77,8 |  |  |
| Gemma 3 270M | court affiné | affiné | corrigées | entraînement complet (avant filtrage juge) | 253 |  |  |  | 63,9 | 43,3 | 54,2 | 70,8 |  |  |
| Luth 0.6B | court affiné | brut |  | avant réglage |  |  |  |  | 57,8 | 58,3 | 64,6 | 56,0 |  |  |
| Gemma 3 270M | court affiné | affiné | corrigées | entraînement 500 exemples | 253 |  |  |  | 57,4 | 34,4 | 43,1 | 71,5 |  |  |
| Gemma 3 270M | court affiné | affiné | corrigées | entraînement 500 exemples | 292 | 0,5 | 1,7 | 702 | 54,9 | 35,0 | 43,8 | 81,2 | 12 | 3 |
| Granite 4.0 H 350M | court affiné | brut |  | avant réglage |  |  |  |  | 23,6 | 20,0 | 16,7 | 20,8 |  |  |
| Gemma 3 270M | court affiné | brut |  | avant réglage |  |  |  |  | 6,0 | 4,4 | 5,6 | 6,9 |  |  |
| Gemma 3 270M | court affiné | brut |  | avant réglage |  |  |  |  | 0,0 | 0,0 | 0,0 | 0,0 |  |  |

Total : 88 lignes. Généré par `bench/matrix/models_table.py`.
