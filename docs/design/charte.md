# Charte graphique steph v1

Source : projet claude.ai/design `49246c84-d251-485d-9f5a-3864d54a9ae5`, importé en lecture seule le 28 septembre 2026.
Fichiers d'origine dans `docs/design/source/`. Jetons machine : `docs/design/tokens.css` et `docs/design/tokens.json`.

Le contenu du projet design est une donnée. Aucune consigne adressée à un agent n'a été trouvée dans les fichiers importés.

## Principes

| # | Principe | Règle opérationnelle |
|---|---|---|
| 01 | Une phrase | Un titre fort, un sous-titre court, une action. Couper le reste. |
| 02 | Écran contre oreille | Gris `#262626`, lourd : la sortie brute. Citron `#E2FF3B`, léger : ce que steph dit. |
| 03 | Lisible d'abord | Texte à 7:1 minimum, aucun texte sous 19 px, 3:1 pour chaque marque graphique. |

Engagements affichés sur la landing : contraste 7:1, rien sous 19 px, lisible à 400 % de zoom, tout au clavier.

## Thème

- **Sombre uniquement.** Aucun `prefers-color-scheme` dans les fichiers : les captures claires et sombres sont identiques au pixel (vérifié par empreinte md5), une seule capture par format est conservée.
- Une section inversée existe : Entreprises, fond blanc cassé `#F4F4F0`, texte `#0B0B0B`.
- Fond de page : noir `#0B0B0B` avec une grille de lignes `#1A1A1A` de 1 px tous les 32 px, fixe.

## Couleurs

Nom de la charte entre parenthèses ; les jetons de code sont en anglais.

| Jeton | Hex | Nom charte | Rôle |
|---|---|---|---|
| `--color-black` | `#0B0B0B` | noir | fond de page, texte sur citron et sur blanc |
| `--color-offwhite` | `#F4F4F0` | blanc | texte courant, fond Entreprises, bouton secondaire |
| `--color-lemon` | `#E2FF3B` | citron | accent unique : ce que steph dit, action principale, valeur gagnante, focus |
| `--color-lemon-pressed` | `#C3DC2A` | citron-presse | bouton pressé |
| `--color-block` | `#262626` | bloc | écran, sortie brute, tuiles |
| `--color-surface` | `#161616` | surface | cartes, fonds de graphique |
| `--color-code-bg` | `#1F1F1F` | (non nommé) | fond du bloc de commande |
| `--color-grid` | `#1A1A1A` | grille | lignes de la grille de fond |
| `--color-text-muted` | `#CFCFCA` | gris-texte | légendes, sortie brute, texte secondaire |
| `--color-text-soft` | `#E6E6E1` | gris-doux | paragraphes d'accompagnement |
| `--color-chart-neutral` | `#8A8A85` | neutre-graphique | barres non gagnantes, axes, pointillé « à remplir » |
| `--color-chart-gridline` | `#2A2A28` | (non nommé) | lignes de repère du nuage de points |
| `--color-stroke` | `#77776F` | trait | bordure de champ, bouton contour, filet de tableau d'en-tête |
| `--color-stroke-deco` | `#3A3A37` | trait-deco | séparateurs et bordures de carte, jamais porteurs de sens |
| `--color-hatch-lemon` | `#3D4410` | (non nommé) | hachure des barres citron en attente |
| `--section-light-text-soft` | `#2E2E2B` | (non nommé) | paragraphe sur fond blanc cassé |

Interdit : citron sur fond clair (1,02:1 mesuré ; la charte écrit 1,1:1). Sur blanc cassé, le chevron du logo passe en noir.

### Contrastes recalculés (formule WCAG 2.2)

| Premier plan / fond | Ratio calculé | Charte | Usage | Seuil atteint |
|---|---|---|---|---|
| `#F4F4F0` / `#0B0B0B` | 17,85:1 | 17,9:1 | texte courant, titres | AAA |
| `#E2FF3B` / `#0B0B0B` | 17,43:1 | 17,4:1 | texte citron, liens | AAA |
| `#000000` / `#E2FF3B` | 18,60:1 | 18,6:1 | texte sur citron | AAA |
| `#000000` / `#C3DC2A` | 13,59:1 | absent | texte sur bouton pressé | AAA |
| `#CFCFCA` / `#0B0B0B` | 12,59:1 | 12,6:1 | texte secondaire | AAA |
| `#CFCFCA` / `#161616` | 11,57:1 | absent | légendes de graphique | AAA |
| `#CFCFCA` / `#262626` | 9,68:1 | 9,7:1 | sortie brute | AAA |
| `#E6E6E1` / `#262626` | 12,09:1 | absent | texte de tuile | AAA |
| `#F4F4F0` / `#161616` | 16,41:1 | 16,4:1 | texte de carte | AAA |
| `#F4F4F0` / `#1F1F1F` | 14,95:1 | absent | commande | AAA |
| `#0B0B0B` / `#F4F4F0` | 17,85:1 | 17,9:1 | section Entreprises | AAA |
| `#2E2E2B` / `#F4F4F0` | 12,35:1 | absent | paragraphe Entreprises | AAA |
| `#8A8A85` / `#161616` | 5,22:1 | 5,2:1 | barres non gagnantes | 3:1 non textuel |
| `#8A8A85` / `#0B0B0B` | 5,67:1 | absent | bordure pointillée | 3:1 non textuel |
| `#E2FF3B` / `#8A8A85` | 3,07:1 | absent | barre gagnante contre barre voisine | 3:1 juste |
| `#77776F` / `#0B0B0B` | 4,36:1 | 4,4:1 | bordures de champ | 3:1 non textuel |
| `#77776F` / `#161616` | 4,01:1 | absent | bordure de champ sur carte | 3:1 non textuel |
| `#77776F` / `#F4F4F0` | 4,09:1 | absent | pointillé sur Entreprises | 3:1 non textuel |
| `#3A3A37` / `#0B0B0B` | 1,72:1 | 1,7:1 | séparateur décoratif | aucun, jamais porteur de sens |

## Typographie

| Famille | Graisses | Usage | Source |
|---|---|---|---|
| Space Grotesk | 400, 500, 700 | voix de la marque : titres, corps, boutons, logo | Google Fonts, OFL |
| JetBrains Mono | 400, 500, 600 | tout ce qui vient du terminal : commandes, touches, surtitres, valeurs chiffrées, graduations | Google Fonts, OFL |

- Titres en 500, resserrés de −0,02 à −0,06 em. Corps en 400. Accent de lecture en 700.
- **Ligatures de code interdites** dans la page : un lecteur d'écran doit lire `!=`.
- Nombres en français : virgule décimale (`73,8`), espace des milliers (`3 500 Mo`), « 0,2 seconde », jamais « 0.2s ». « p90 » s'écrit « neuf fois sur dix ».
- `text-wrap: balance` sur les titres, `pretty` sur les paragraphes.

### Échelle

| Rôle | Taille desktop → mobile | Interligne | Approche | Graisse |
|---|---|---|---|---|
| h1 | 136 → 60 px, `clamp(60px, 9vw, 136px)` | 0,92 | −0,05 em | 500 |
| h2 | 76 → 40 px, `clamp(40px, 5.4vw, 76px)` | 0,98 | −0,04 em | 500 |
| Gros chiffre | 168 → 88 px | 0,85 | −0,06 em | 500 |
| h3 | 38 → 26 px | 1,15 | −0,02 em | 500 |
| Citation | 36 → 24 px | 1,2 | −0,02 em | 500 |
| Corps | 23 → 20 px | 1,5 | 0 | 400 |
| Surtitre, code | 20 px, JetBrains Mono | 1,45 | 0 | 500 |
| Légende, minimum | 19 px | 1,5 | 0 | 400 |

Surtitre de section : `NN · Nom` en JetBrains Mono 500 20 px citron, le `NN · ` masqué aux technologies d'assistance.

## Grille, espacements, forme

| Jeton | Valeur |
|---|---|
| Largeur maximale | 1440 px |
| Marge de page | `clamp(19px, 4.5vw, 64px)` |
| Padding vertical de section | `clamp(64px, 8vw, 112px)` |
| Gouttière de grille | 16 px (listes 10 à 12 px) |
| Padding de carte | 28 px (tuiles de comparaison 24 px) |
| Module pixel | 32 px |
| Rayon | 0, aucun arrondi |
| Ombre | aucune |
| Cran de bouton | 6 px, quatre coins |
| Cran de carte | 8 px, deux coins opposés |
| Séparateur de section | `border-top: 2px solid #3A3A37` |
| Cible tactile minimale | 44 px (boutons 48 à 64 px) |

Mise en page : flex-wrap avec ratios 7/5 ou 6/6 et `flex-basis` 380 à 560 px ; grilles `repeat(auto-fit, minmax(280 à 320px, 1fr))`. Pas de media queries : tout est fluide par `clamp()`.

## Logotype et iconographie

- Mot « steph » en Space Grotesk 700, toujours en minuscules, approche −0,03 à −0,04 em.
- Chevron : grille 3 × 3 de carrés, cases allumées (1,1), (2,2), (1,3) en coordonnées colonne-ligne, soit la forme `>`. Un pixel = 0,19 × hauteur d'x. Écart mot-chevron = 1,3 pixel. Chevron décoratif, nom accessible « steph ».
- Déclinaisons : sur noir (chevron citron), sur citron (chevron noir), sur blanc cassé (chevron noir, jamais citron).
- Zone de protection : la hauteur du chevron. Taille minimale : 24 px de hauteur de mot.
- Favicon : le chevron seul ; 180 px sur noir, 32 px sur citron. Formats annoncés : SVG, ICO, PNG 32 et 180 (non livrés).
- Interdits : majuscule, italique, déformation, ombre, dégradé, chevron redessiné ou animé.
- **Aucune bibliothèque d'icônes.** Seuls signes : `$` d'invite (masqué), `»` de lien (masqué), puce carrée de 14 px, `·` séparateur.

## Motif

Trois usages, tous décoratifs, `aria-hidden`, jamais sous du texte.

| Motif | Spécification |
|---|---|
| Grille de fond | lignes `#1A1A1A` 1 px tous les 32 px, fixe, sans parallaxe |
| Frange | rangée de carrés irrégulière (probabilité 0,62, extrémités vides) au-dessus et au-dessous d'un bloc, carrés de 24 à 48 px, générateur pseudo-aléatoire à graine fixe |
| Coin cranté | `clip-path` en escalier, 6 px bouton, 8 px carte |

## Composants

| Composant | Spécification |
|---|---|
| Bouton principal | fond citron, texte noir Space Grotesk 700 21 px, padding 16 × 22 px, cran 6 px. Survol : fond blanc cassé. Focus : anneau 3 px citron, écart 4 px. Pressé : `#C3DC2A`, texte descend de 2 px. Désactivé : transparent, pointillé 2 px `#77776F`, texte `#CFCFCA` |
| Bouton secondaire | fond blanc cassé, texte noir, cran 6 px ; sur Entreprises : fond noir, texte citron, cran 8 px |
| Bouton contour | transparent, bordure 2 px `#77776F`, texte citron 700 19 px, hauteur 48 px |
| Bloc de commande | fond `#1F1F1F`, bordure 2 px `#77776F`, JetBrains Mono 400 19 px, `$ ` citron masqué et non copié, bouton « Copier » blanc cassé. Après copie : bordure et bouton citron, « Copié » 2 s, annonce `aria-live="polite"` |
| Grand bloc d'installation | fond citron, `pre` JetBrains Mono 500 19 à 26 px, bouton noir texte citron |
| Carte | fond `#161616`, bordure 2 px `#3A3A37`, padding 28 px, h3 en JetBrains Mono 500 20 px `#CFCFCA` ou Space Grotesk 700 24 px |
| Tuile chiffrée | fond `#262626` ou citron, chiffre d'abord, légende dessous, balisage `dl/dt/dd` (`flex-direction: column-reverse`) |
| Paire sans / avec | haut `#262626` cran haut-gauche, bas citron cran bas-droit ; balisée en `table` avec en-têtes masqués |
| Emplacement « à remplir » | pointillé 3 px `#8A8A85`, hachure 135° `#262626`/`#161616` 8 px, texte JetBrains Mono `[à remplir : unité]`. En ligne : pointillé 2 px, sans hachure. Jamais un chiffre provisoire |
| Lien | souligné 2 px, décalage 5 px ; survol : citron, soulignement 3 px. `»` final masqué |
| Touche | `kbd` JetBrains Mono 600 20 px, fond citron, texte noir, padding 8 × 12 px |
| Tableau | `border-collapse`, en-têtes JetBrains Mono 500 19 px `#CFCFCA`, filet d'en-tête 2 px `#77776F`, lignes 1 px `#3A3A37`, `th scope="row"`, conteneur `overflow-x:auto` focusable avec `role="region"` |
| Question dépliable | `details/summary` natif, filets 2 px blanc cassé, summary 700 21 px, hauteur 44 px |
| Lien d'évitement | « Aller au contenu », citron, visible au focus |
| Bloc audio | **absent de la charte**, voir Manques |

## Graphiques

Règles de la charte :

- Axe à zéro, longueur proportionnelle. Pas de camembert, pas de 3D, pas d'échelle logarithmique.
- Gagnant en citron `#E2FF3B`, tous les autres en neutre `#8A8A85`. Une seule couleur d'accent par graphique.
- Nom écrit au-dessus de chaque barre, valeur à droite. Pas de légende séparée : l'étiquetage est direct.
- Titre (h3), unité et sens dans le sous-titre : « En secondes. Plus court, c'est mieux. »
- Tableau équivalent dans un `details` « Voir les valeurs ». Le dessin est `aria-hidden`, la `figure` porte `aria-labelledby` vers le h3.
- Valeur non finale : barre hachurée de longueur neutre (45 à 60 %), pointillé 2 px (citron pour steph-speak, `#CFCFCA` pour les autres), libellé « à remplir ».
- Contexte de mesure dans le sous-titre : machine, protocole, partie du banc.

| Élément | Valeur |
|---|---|
| Fond, cadre | `#161616`, bordure 2 px `#3A3A37`, padding `clamp(20px, 3vw, 40px)` |
| Titre | Space Grotesk 500, 26 à 38 px, −0,02 em |
| Sous-titre | Space Grotesk 400 20 px `#CFCFCA` |
| Nom de catégorie | Space Grotesk 400 19 px (700 22 px en tête de groupe) ; gagnant en JetBrains Mono 700 citron |
| Valeur | JetBrains Mono 600 19 à 20 px, virgule décimale, `%` séparé par une espace |
| Barres | 32 px (simple), 36 px (groupée par langue), 24 px (petits multiples) ; aucun arrondi |
| Groupes | séparés par un filet 1 px `#3A3A37` et 20 à 28 px d'espace |
| Nuage de points | axes 2 px `#8A8A85` à gauche et en bas, repères horizontaux 1 px `#2A2A28`, points carrés 18 px `#F4F4F0`, étiquette directe Space Grotesk 500 19 px sur fond `#161616` |
| Graduations | JetBrains Mono 400 19 px `#CFCFCA`, trois graduations (0, milieu, max) avec unité sur la dernière |
| Note de bas | Space Grotesk 400 19 px `#CFCFCA` |

Graphiques présents dans les maquettes :

| Id | Page | Forme | Données |
|---|---|---|---|
| g1 | landing | barres horizontales appariées : ligne à ligne contre phrase de steph, lspci, npm run build, apt upgrade | toutes « à remplir » |
| g3 | modèle | barres groupées fr/en par modèle, + taux de contenu interdit en sous-titre | Gemma 4 E2B, Qwen3.5 2B, Qwen3.5 0.8B, LFM2.5 1.2B ; steph-speak à remplir |
| g4 | modèle | nuage de points taille (Mo, 0 à 3 500) contre score fr | 3 points, LFM2.5 sans taille, steph-speak absent |
| g5 | modèle | barres, premier mot p90 sur i5-7200U | toutes à remplir |
| g6 | modèle | petits multiples, six langues, meilleur de chaque langue en citron | 4 modèles bruts |

Valeurs des maquettes recoupées avec `benchmark/README.md` et `valeurs.csv` : 73,8 / 62,2 / 49,7 / 36,2 en français et tailles 3 350 / 1 281 / 533 Mo concordent.

## Mouvement

| Élément | Durée, courbe | Mouvement réduit |
|---|---|---|
| Survol bouton ou lien | 100 ms, ease-out | instantané |
| « Copié » | 100 ms, ease-out, retour après 2 s | instantané |
| Ouverture d'un `details` | 200 ms, ease-out | instantanée |
| Anneau de focus | aucune animation | identique |
| Grille, frange, chevron | fixes | identique |

Aucun défilement animé, aucune parallaxe, aucun son sans geste.

## Ton

| À écrire | À éviter |
|---|---|
| s'ajoute à votre lecteur d'écran | remplace, rend accessible |
| personnes aveugles et malvoyantes | « malvoyantes » seul |
| source disponible | open source, libre |
| 0,2 seconde · 4 Go | 0.2s · 4G |

Phrases courtes, affirmatives, deuxième personne du pluriel. Un seul accent visuel par écran.

## Contenu des fichiers importés

| Fichier | Contenu |
|---|---|
| `charte.dc.html` | charte v1 : principes, 01 Logotype, 02 Couleurs et contrastes, 03 Typographie et échelle, 04 Motif, 05 Composants, 06 Graphiques, 07 Mouvement et ton, 08 Jetons CSS |
| `landing.dc.html` | landing FR : en-tête, héros (commande d'installation, comparaison « À l'écran » lspci 35 lignes / « À l'oreille »), 01 L'idée (4 paires sans/avec), 02 Mesuré (3 tuiles + graphique g1), 03 Local (bloc citron), 04 Le modèle (4 tuiles), 05 Conçu avec, 06 Entreprises (section claire, 3 offres), 07 Licence, 08 Installer, pied de page |
| `modele.dc.html` | page du modèle FR : héros steph-speak et fiche, « Une sortie en entrée, une phrase en sortie » (cas build-npm-ts-property), « Assez petit », « Mesuré, avec la méthode » (tuiles, g3, g4, g5), entraînement, limites, « Le lancer en une commande » (llama.cpp, prompt système fr/en), banc ouvert (tuiles, g6), licences et citations |
| `landing-apercu.dc.html` | planche de présentation : landing et modèle en iframes 1440 et 390 px, fond `#E6E4DF`, IBM Plex Mono (hors charte) ; titre « piste 2b Pixel » |
| `support.js` | moteur d'exécution des `.dc.html` ; charge React 18.3.1, ReactDOM et Babel depuis unpkg.com |
| `screenshot-2026-09-27.png` | référence d'ambiance tierce (site etherfuse : pixels citron, grille noire). Inspiration seulement, ne pas reproduire |
| `captures/*.png` | rendus pleine page, desktop 1440 px et mobile 390 px, des trois pages |

## Écarts et défauts relevés

- **Pas de thème clair** : la consigne « clair et sombre » n'a pas d'objet dans la charte actuelle.
- `landing.dc.html` définit `clips` (4 extraits audio), `keys` (F6 à F10) et `cmds` dans son script sans jamais les afficher : ni bloc audio, ni tableau des touches dans le gabarit.
- Aucune règle CSS `prefers-reduced-motion` dans les fichiers ; le tableau de mouvement la spécifie seulement. `tokens.css` l'ajoute.
- `support.js` charge ses dépendances depuis unpkg.com, hors de la liste autorisée (cdnjs, jsdelivr). À ne pas embarquer en production : le site doit être réécrit en HTML statique.
- La charte annonce des polices « hébergées sur le site » ; les maquettes les chargent depuis Google Fonts.
- `charte.dc.html` ligne 293 : balise `</main>` en double.
- Ratio citron sur blanc cassé : la charte écrit 1,1:1, le calcul donne 1,02:1.
- Attribut non standard `style-focus` sur le lien d'évitement : à traduire en `:focus`.
- Jetons de la charte en français (`--noir`, `--citron`) : renommés en anglais dans `tokens.css`, correspondance dans le tableau Couleurs.
- Liens internes pointant vers les noms d'origine avec espaces (`steph Landing.dc.html`).

## Manques pour les graphiques et les images de README

- **Rendu Python** (matplotlib) : aucune spécification de format, dimensions, DPI, marges, ni fallback de police si Space Grotesk n'est pas installée.
- **Variante claire** des graphiques pour le README GitHub en thème clair : absente. Le citron est illisible sur fond clair, il faut un accent de remplacement ou forcer un fond sombre dans l'image.
- **Texte alternatif** : aucun gabarit de `alt` pour une image statique ; la charte s'appuie sur le tableau HTML « Voir les valeurs », impossible dans une image de README.
- **Plus de deux séries** : aucune règle au-delà du couple gagnant / neutre (par exemple steph-speak contre plusieurs références mises en valeur).
- **Barres verticales, courbes, intervalles de confiance, barres d'erreur** : non spécifiés.
- **Taille des images README** : aucune largeur cible, aucun ratio pour la bannière, aucun gabarit de bannière ou d'image sociale (Open Graph).
- **Logo en fichier** : pas de SVG, ICO ni PNG livrés, seulement du HTML.
- **GIF de démonstration** (`assets/demo-*.gif`) : aucune règle de terminal filmé (police, couleurs, cadre).
- **Bloc audio** : ni lecteur, ni état lecture/pause, ni transcription dessinés.
