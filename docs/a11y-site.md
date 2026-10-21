# Accessibilité du site (W1, passe automatique)

Serveur local de `site/public`, Chromium via Playwright, axe-core (npm) avec les jeux de règles wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa, wcag2aaa et best-practice. Captures dans `docs/a11y-site/`.

| Contrôle | FR | EN | Preuve |
|---|---|---|---|
| axe, bureau 1440 px | 0 violation | 0 violation | `docs/a11y-site/fr-desktop.png`, `en-desktop.png` |
| axe, mobile 390 px | 0 violation | 0 violation | `fr-mobile.png`, `en-mobile.png` |
| Clavier seul : 15 arrêts de tabulation, premier = lien d'évitement, indicateur de focus présent partout | oui | oui | script Tab, styles calculés |
| Zoom 400 % (fenêtre 320 px) : débordement horizontal | 0 px | 0 px | `fr-zoom400.png`, `en-zoom400.png` |
| Mouvement réduit : animations infinies en cours | 0 | 0 | `document.getAnimations()` |
| Contraste renforcé (AAA) | couvert par axe | couvert par axe | règle `color-contrast-enhanced` |

## Défauts trouvés et corrigés

- Zoom 400 % : 67 px de débordement horizontal, causés par les barres « à remplir » du graphique des durées d'écoute (largeur minimale fixe). Barres remplacées par de vraies mesures en largeur relative (`site/public/style.css`, `.bar-val`).
- Textes « à remplir » encore publics (graphique, tableau, adresse de méthode, taille d'installation) : remplacés par les mesures et liens réels.

## Non vérifié

- VoiceOver, NVIDIA/Orca, NVDA : jamais lancés.
- Tableau équivalent des graphiques : présent dans la page, lu par axe seulement (structure), pas écouté.
- Langue des passages, mode lecteur : non testés à la main.
- Page du modèle (`/modele/`, `/en/model/`) : non auditée et non à jour (voir rapport Z3), plus liée depuis la landing.
