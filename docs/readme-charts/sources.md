# Sources des chiffres du README (images et prose)

Trace chaque valeur numérique ajoutée ou corrigée dans les images et le texte du README.
Correction du 2026-09-28 (tâche D3) : R1 (réentraînement final, le journal de mission interne (non publié)
ligne R1) est fait, **steph-speak v1.0 est le modèle livré** (décision autonome de
l'utilisateur, recette `r1-i1-l07`) ; les chiffres ci-dessous remplacent ceux du modèle
précédent P17, gardé pour comparaison. Ce n'est pas encore le chiffre final de tout : la
mesure de comparaison globale (Q3) et le banc multilingue (L2) restent à faire, le rescore
sur le banc v3 (X3) est à part et non repris ici, et le site plus les dernières retouches
d'images (M4) viendront après Q3/L2/X3. Le modèle reste privé (Hugging Face) : la
publication (A10) n'a pas eu lieu.

## Modèle R1 - steph-speak v1.0 (graphiques `docs/readme-charts/data.json`)

Recette retenue par la règle T5 (le journal de mission interne (non publié)) : `r1-i1-l07`, interpolation à
lambda 0,7 vers P17 sans réentraînement supplémentaire, non inférieure à P17 (v2 84,5 contre
87,7, IC à 95 % [-11,1 ; 2,8]).

| Valeur | Chiffre retenu | Source | Note |
|---|---|---|---|
| GGUF sur disque | 223 Mo | `bench/matrix/results/finetune/r1/r1-summary.json` → `deliverable.size_bytes` (222 662 112 octets) | sha256 `45414bd2…`, 402/402 tenseurs identiques au GGUF P17 `d548f3fc` ; même poids que P15/P17 |
| Qualité v2 totale | 84,5 | `bench/matrix/results/finetune/r1/r1-summary.json` → `models.r1-i1-l07.v2` | recoupé le journal de mission interne (non publié) ligne R1 (« v2 84,5 contre 87,7 ») ; contre P17 87,7 (régression assumée, non-infériorité statistique retenue) |
| Qualité v2, contrôle (holdout) | 69,4 | idem, `models.r1-i1-l07.holdout` | jeu jamais utilisé pour régler le modèle ; contre P17 80,6 |
| Qualité « tel que dit » (v2_spoken) | 87,2 | idem, `models.r1-i1-l07.spoken` | non affiché dans les graphiques actuels, cité pour mémoire |
| Questions (qa0/qa1/qa2) | qa0 0 %, qa1 100 %, qa2 100 % | idem, `models.r1-i1-l07.qa` | **qa0 raté sur les 3 graines** (le journal de mission interne (non publié) ligne R1 : « corrige "titel" en "Titl" ») ; P17 tenait qa0 à 100 % |
| RAM (pic), réglage recommandé | 545 Mo (544 en répétition, ≈ 0,55 Go) | `bench/matrix/results/finetune/r1/i5/r1.json` et `r1-rep.json` → `ram_peak_mb` | mesuré directement sur le GGUF livré (pas un proxy P15) ; repos avant 488-490 Mo ; réglage `-c 8192 --parallel 2 --cache-ram 0` |
| Premier mot p90 (i5, sans TTS, 36 cas + 3 questions) | 1,40 s (1,406 s puis 1,394 s en répétition) | `bench/matrix/results/finetune/r1/i5/r1.json` et `r1-rep.json` → `ttft_p90` | `llama-b11205`, `-c 8192 --parallel 2 -b 512 -ub 512 -t 4 --cache-ram 0` ; cible A9 < 1 s **non tenue** ; contre P17 1,283 s/1,401 s (même harnais, `p17.json`/`p17-rep.json`) |
| Premier son p90 (i5, audio réel, 33 fixtures P19) | 0,189 s (~0,19 s) | `docs/p14-final.md:14,51` (tableau section 2, colonne « Son audible p90 ») | mesure d'architecture TTS partagée (P19), indépendante du modèle affiné ; non remesurée pour R1 ; cible A9 < 0,3 s tenue sur P17, présumée inchangée |
| Inventions/36, sans garde-fou d'ancrage | 4,0 (moyenne 3 graines 7/42/123 : 5/3/4) | `bench/matrix/results/finetune/r1/eval/judge-r1-i1-l07.txt` ; recoupé `r1-summary.json` → `models.r1-i1-l07.inv` | cible A9 ≤ 1 **non tenue** ; contre P17 5,33 (`judge-p17.txt`) |
| Inventions/36, avec garde-fou d'ancrage P13 | 3,7 (moyenne 3 graines 7/42/123 : 4/4/3) | `bench/matrix/results/finetune/r1/eval/judge-r1-i1-l07-ground.txt` ; recoupé `r1-summary.json` → `models.r1-i1-l07.inv_ground` | `steph.grounding.ground()` appliqué après génération ; contre P17 4,33 (`judge-p17-ground.txt`, proche de l'ancien 4,3 de `docs/p14-final.md`) |

**Verdict des 3 critères A9 sur R1** : premier son tenu (architecture inchangée), premier
mot et inventions non tenus, comme sur P17. R1 reste néanmoins retenu : non inférieur à P17
selon la règle T5, et seul modèle entraîné aux fonctionnalités et aux questions en anglais.
Ce n'est pas caché dans le README : les chiffres ci-dessus sont ceux du modèle réellement
livré, pas encore publié sur Hugging Face.

## Steph Speak Bench, score FR/EN (prose du README)

**Le chiffre FR 51,6 / EN 44,5 initialement transmis ne vient PAS de P15, P17 ni R1** : il
provient de la tâche C3 (le journal de mission interne (non publié)), mesuré sur une « soupe Granite »
antérieure au garde-fou d'ancrage P13, à P15, à P17 et à R1 (fichiers
`benchmark/results/steph-protocol/20260927-152901..._fr_test.json` /
`..._en_test.json`, champ `notes` : « soupe uniforme 4 graines (A12), fusion LoRA (A6),
candidat principal »). Ce chiffre n'est plus le dernier disponible.

**Mesure R1 réelle, modèle livré** (split test complet, 62 cas/langue,
`bench/matrix/results/finetune/r1/r1-summary.json` → `models.r1-i1-l07.test`, recoupé
le journal de mission interne (non publié) ligne R1 : « Steph Speak Bench test FR 44,8 contre 38,5, EN 47,2
contre 39,6 (non significatif) ») :

| Langue | Score, protocole steph (prompt de production) | Score, protocole standard |
|---|---|---|
| FR | 44,8 % | 45,4 % |
| EN | 47,2 % | 49,4 % |

Retenu pour le README : **protocole steph** (le prompt réellement utilisé en production),
soit **FR 44,8 % / EN 47,2 %**, avec la mention explicite « steph-speak v1.0 ». Pour mémoire,
P17 (avant R1) donnait FR 38,5 % / EN 39,6 % au même protocole et au même fichier
(`models.p17.test`) : la différence n'est pas significative (mission-finetune.md ligne R1).
Ce 38,5 % diffère légèrement du 38,0 % cité dans une correction précédente de ce fichier
(mesure L2p, le journal de mission interne (non publié), harnais distinct) ; retenu ici : la valeur du même
fichier `r1-summary.json` que R1, pour une comparaison appariée cohérente.

`docs/model-card-draft.md:75,130-131` précise que le score « Steph Speak Bench FR/EN »
officiel de la fiche modèle doit être cité avec le chiffre de R1 : c'est désormais fait
ci-dessus, la fiche modèle elle-même (I2, A10) reste hors périmètre de cette correction.

## Nouvelle architecture (prose des sections « Comment ça marche » et « Rien ne sort de la machine »)

| Valeur | Chiffre retenu | Source | Note |
|---|---|---|---|
| Part de TermSpeak résolue en code, sans appel au modèle (P12) | 79 → 117 sur 192 (41 % → 61 %) | le journal de mission interne (non publié) | **biais signalé par la source elle-même** : « les regex ont été écrites en lisant aussi le split test de TermSpeak, le 61 % est optimiste » ; repris tel quel dans le README avec la réserve |
| Garde-fou d'ancrage (P13) : inventions retirées hors ligne | 112/169 confirmées retirées (nombres 26/28, noms 24/35) ; 0/540 faits vrais coupés à tort sur la soupe | le journal de mission interne (non publié) | qualité v2 de la soupe passée de 80,4 à 83,2 grâce au garde-fou |
| Voix partagée entre fenêtres (Q2a) : chevauchement audio | 0 % à 2/4/8 fenêtres (contre 48/74/79 % avant) | le journal de mission interne (non publié) | mesuré sur Mac, `bench/perf/results/mac-q2a-{before,after}.json` |
| Voix partagée entre fenêtres (Q2a) : RAM à 8 fenêtres | 530 Mo (contre 1 535 Mo avant) | le journal de mission interne (non publié) | ~33 Mo/fenêtre + 190-260 Mo pour le service, au lieu de ~200 Mo/fenêtre |
| Déchargement du serveur au repos (Q2b) | 3 643 Mo avant déchargement → 0 Mo (processus arrêté) | le journal de mission interne (non publié) | mesuré avec un réglage de test à 9 s (au lieu des 10 min par défaut, `llm_idle_unload_minutes`), mécanisme identique |
| `steph setup` (B6) | liste tout le catalogue, recommande selon le matériel détecté, bloque les options impossibles avec la raison, télécharge avec progression | le journal de mission interne (non publié) | |
| Installeur (B7) : modèle par défaut aujourd'hui | Gemma 4 E2B, tant que le modèle universel n'est pas publié | le journal de mission interne (non publié) | confirme que les 3,6/4,4 Go actuels du README restent exacts et inchangés |

## Installation (image « Installation », graphique `install()`)

| Valeur | Chiffre retenu | Source | Note |
|---|---|---|---|
| Taille actuelle, sans GPU / avec NVIDIA | 3,6 Go / 4,4 Go | `docs/setup-ux.md:95,194` | inchangé, déjà exact (Gemma 4 E2B par défaut) |
| Première phrase de steph pendant l'installation | 9,9 s après le début de l'installation | `docs/setup-ux.md:184,212` | mesuré sur Mac, uv neuf, sans Homebrew ; avant llama.cpp (11,0 s) et le modèle (12,4 s) |
| Désinstallation | 1,6 s, 1,6 Go libérés | `docs/setup-ux.md:216` | `steph uninstall`, Mac, pseudo-TTY |
| Futur modèle universel, poids modèle + voix + llama.cpp, sans GPU | 223 + 63 + 17 ≈ 300 Mo | `src/steph/data/catalog.json:26,51` (`size_mb`) + `docs/setup-ux.md:42` (« même vitesse que CPU (17 Mo, 1,4 s) », comparaison citée dans la ligne de mesure Vulkan) | image `install()` mise à jour avec ce total ; ne compte pas Python/uv, dont le poids exact avec ce modèle n'est pas mesuré |
| Futur modèle universel, avec NVIDIA (CUDA) | 223 + 63 + 766 ≈ 1,05 Go | idem + `docs/setup-ux.md:43,95` (« 172 Mo + 594 Mo de cudart », recoupé « CUDA 766 Mo » du défaut M2) | `available: false`, pas encore publié (R1 fait, modèle retenu ; A10 reste à faire) ; ces deux totaux sont un calcul, présenté comme tel dans l'image, pas une mesure d'installation réelle |

## Matériel (image « Matériel », graphique `hardware()`)

| Valeur | Chiffre retenu | Source | Note |
|---|---|---|---|
| i5-7200U (CPU seul, sans GPU), futur modèle universel : RAM | ≈ 545 Mo | voir tableau « Modèle R1 » ci-dessus | |
| i5-7200U : premier mot p90 | 1,4 s | voir tableau « Modèle R1 » ci-dessus | |
| i5-7200U : premier son p90 | 0,19 s | voir tableau « Modèle R1 » ci-dessus | mesure d'architecture partagée, non spécifique à R1 |
| Mac M3 Pro, Metal, Gemma 4 E2B : premier mot p90 | 0,68 s | `docs/readme-charts/data.json` → `ttft_p90_mac.gemma4_e2b` (source `bench/matrix/results/mac-m3pro-metal-gemma4e2b.json`) | modèle par défaut aujourd'hui, pas le modèle universel (aucune mesure Mac pour R1) |
| Mac M3 Pro, Gemma 4 E2B : RAM au pic | 3,4 à 3,7 Go | `docs/readme-charts/data.json` → `ram_mb.gemma4_e2b_metal` (`bench/perf/results/mac.json` : 3 445 et 3 577 Mo ; même fichier, jusqu'à 3 673 Mo, Metal, `llama-server` de production) | le chiffre CPU seul (4 784 Mo, `ram_mb.gemma4_e2b`) n'est plus affiché comme Metal |
| NVIDIA T600, 4 Go, Gemma 4 E2B : résumé moyen | 1,5 s | README « Choix du modèle », `docs/readme-charts/build_readme.py` (fonction `bench()`) | même chiffre déjà affiché dans l'image « Choix du modèle » |
| Niveaux matériel N1-N4 du catalogue | mesurés sur une seule machine réelle (rtx3060, AMD Ryzen 5 5600), niveaux simulés par cgroup | `options.json:2` (`measured_on`) du dossier de banc vocal de la machine rtx3060 sous `docs/voice-bench/` | pas 4 machines physiques distinctes ; non utilisé comme tel dans l'image pour ne pas laisser croire à 4 bancs séparés |

## Non repris dans les images (hors scope ou non mesuré)

- Durée totale d'une future installation avec le modèle universel : **non mesurée**, non
  inventée.
- Réponse exacte de steph-speak v1.0 (R1) sur le cas d'exemple `fx17` (image `example`) :
  aucun fichier de résultat R1 ne garde le texte généré par cas (seuls les scores agrégés
  sont conservés, `bench/matrix/results/finetune/r1/eval/score-r1-i1-l07.json`) ; le
  graphique garde son bloc « à remplir », légitimement. Faire tourner le modèle livré sur ce
  cas précis est le travail de M4 (le journal de mission interne (non publié) ligne M4 : « phrases d'exemple
  de sortie de steph régénérées en faisant tourner le modèle livré »), pas de cette
  correction D3.
- Vitesse Mac du modèle livré (`ttft_p90_mac.steph`) : aucune mesure R1 trouvée ; reste
  « à remplir ».
