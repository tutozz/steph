# TUI accessible pour `steph setup` et le menu F6 (M6)

Recherche et conception du 2026-09-28. Mise en œuvre : `src/steph/tui.py`,
`src/steph/setup_tui.py`, `src/steph/menu.py`, `src/steph/proxy.py`.

## 1. Ce que vivent les lecteurs d'écran dans un TUI plein écran

### Constats

| # | Constat | Source |
|---|---|---|
| R1 | Une interface en ligne (question, réponse, ajout en bas) est ce que les lecteurs d'écran suivent le mieux : le texte arrive dans l'ordre du temps. | Sampath, Merrick, Macvean, *Accessibility of Command Line Interfaces*, CHI 2021 ; xogium, *The text mode lie* |
| R2 | Les TUI modernes (Ink, Bubble Tea, tcell) traitent le terminal comme une grille de pixels : le curseur saute à chaque redessin, le lecteur d'écran lit n'importe quoi. | xogium, *The text mode lie*, relayé par OSnews |
| R3 | Irssi reste lisible parce qu'il utilise les régions de défilement VT100 au lieu de redessiner tout l'écran. | xogium, *The text mode lie* |
| R4 | Le mode recommandé par les lecteurs en console (Speakup, Fenrir) pour un menu : suivre le curseur ou la surbrillance. Un menu dont le curseur reste ailleurs se lit « n'importe comment ». | Ubuntu Wiki, *Accessibility/doc/Speakup* ; liste vinux-support, *Using CLI programs with speakup* |
| R5 | Le mode « lecteur d'écran » d'un terminal ou d'une app doit garder le vrai curseur sur le texte focalisé et décrire ce qui change. | croft, issue #621 ; Orca (stablyai), issue #19670 |
| R6 | VoiceOver dans Terminal.app lit mal les applications plein écran (vim) : pas de sémantique, relecture incomplète ; des utilisateurs lui préfèrent TDSR, qui lit la sortie au fil de l'eau. | AppleVis, *How can you even use terminal daily with VoiceOver* ; AppleVis, *Better experience in Terminal with VoiceOver* |
| R7 | L'écran alternatif (nano, less, vim) remplace l'écran principal le temps de l'application, puis le restaure. | Apple, *Display or hide the alternate screen in Terminal* |
| R8 | Tableaux, cadres et logos ASCII gênent : les rendre optionnels, offrir un mode minimal (`--simple`, `--a11y`). | AFixt, *Accessible by Design: Improving CLIs* ; Sampath et al. 2021 |
| R9 | L'installateur Debian propose deux frontends : `text` (question-réponse) et `newt` (boîtes, flèches + Entrée, Tab entre éléments) ; newt sert surtout avec une plage braille. | Debian Wiki, *DebianInstaller/Accessibility* ; Debian, manuel d'installation §5.2 |
| R10 | Orca est piloté par `org.gnome.desktop.a11y.applications screen-reader-enabled` et tourne comme processus `orca`. | Orca list, octobre 2021 ; Debian Wiki, *Accessibility/Orca* |
| R11 | Détecter le TTY, respecter `NO_COLOR` et `TERM=dumb`, une ligne par événement. | clig.dev (déjà cité dans `docs/setup-ux.md`) ; no-color.org |

### Techniques retenues

| Technique | Pourquoi | Constat |
|---|---|---|
| Curseur système visible, posé au début de la ligne focalisée après chaque mouvement | les lecteurs et les loupes (Zoom macOS) suivent le curseur | R4, R5 |
| Mise à jour partielle : la description, puis l'ancienne ligne, puis la nouvelle ; jamais d'effacement global après l'ouverture | pas de redessin qui fait sauter le curseur | R2, R3 |
| Focus porté par un signe `›` en plus de la couleur (vidéo inverse sans couleur) | la couleur ne porte jamais seule le sens | R8, charte |
| Chaque changement de focus dit par la voix de steph : libellé court et état | l'utilisateur n'a pas besoin de lire l'écran | R6 |
| Écran alternatif annoncé à l'ouverture, restauré à la sortie, y compris sur exception et Ctrl+C | le shell et l'historique restent intacts | R7 |
| Repli automatique en mode ligne | le mode ligne est ce que les lecteurs lisent le mieux | R1, R9 |
| Pas de cadre, pas de tableau, logo sur une ligne | rien à épeler | R8 |

### Pourquoi pas curses

`curses` est dans la bibliothèque standard, mais :

- son optimiseur de rafraîchissement décide seul quelles cellules réécrire et où laisser le
  curseur : impossible de garantir « une ligne par mouvement » ;
- il prend le terminal entier (`initscr`) : le menu F6 vit à l'intérieur du proxy, qui relaie
  déjà les octets du shell, et ne peut pas lui céder le terminal ;
- il ne sait pas écrire les couleurs de la charte en truecolor sans `init_color`, souvent refusé.

Le rendu est donc écrit en séquences ANSI directes, avec `termios` pour le mode brut :
aucune dépendance ajoutée.

## 2. Repli en mode ligne

Ordre de décision (`tui.ui_mode`) :

| # | Condition | Mode | Raison annoncée |
|---|---|---|---|
| 1 | pas de terminal (entrée ou sortie) | ligne | `no_tty` ; pour `steph setup` sans `/dev/tty`, rien n'est écrit (B8b inchangé) |
| 2 | `TERM` vide ou `dumb` | ligne | `dumb` |
| 3 | `ui = "line"` dans `config.toml` ou `STEPH_UI=line` | ligne | `user` |
| 4 | `ui = "tui"` ou `STEPH_UI=tui` | plein écran, même avec un lecteur d'écran | `user` |
| 5 | lecteur d'écran détecté | ligne | `screen_reader` |
| 6 | sinon | plein écran | - |

Détection du lecteur d'écran (`tui.screen_reader_active`), chaque sonde bornée à une seconde :

| Système | Sonde | Nom retourné |
|---|---|---|
| macOS | processus `VoiceOver` (`pgrep -x VoiceOver`) | VoiceOver |
| macOS | `defaults read com.apple.universalaccess voiceOverOnOffKey` vaut `1` | VoiceOver |
| Linux | processus `orca` | Orca |
| Linux | `gsettings get org.gnome.desktop.a11y.applications screen-reader-enabled` vaut `true` | Orca |
| Linux | `/sys/accessibility/speakup` existe (module noyau chargé) | Speakup |
| Linux | processus `brltty` | BRLTTY |

Une sonde en faute (binaire absent, délai dépassé) compte comme « pas de lecteur ». Une valeur
`defaults` périmée à `1` fait basculer en mode ligne à tort : erreur sans danger, le mode
ligne reste complet.

`NO_COLOR` ne change pas le mode : le plein écran reste, sans couleur ; le focus passe en
vidéo inverse et garde le signe `›`.

## 3. Conception

### `steph setup` plein écran

```
 steph ›  Configuration                                  étape 2 sur 6
                                                                         
Modèle de langage                                                        
                                                                         
› 1  Gemma 4 E2B            recommandé                                   
  2  Granite 4.2 1B                                                      
  3  Qwen 3 8B              bloqué : hors de portée de cette machine     
                                                                         
3 200 Mo. Recommandé pour cette machine.                                 
                                                                         
↑↓ choisir · Entrée valider · 1-9 aller · ? aide · Échap quitter          
```

- Écrans, dans l'ordre : fichier existant (modifier ou garder), modèle, voix, débit,
  niveau de détail, touches (garder ou choisir, puis capture touche par touche),
  confirmation (résumé, Enregistrer ou Quitter sans enregistrer).
- État d'une option : `recommandé` (noir sur citron), `non recommandé` (gris), `bloqué : raison`
  (gris, validation refusée et raison dite), `actuel`. Le texte d'état est toujours écrit :
  la couleur ne porte jamais seule le sens.
- Une option bloquée reste focalisable : on entend sa raison.
- Téléchargements après la sortie du plein écran : la progression de `fetch` s'écrit en
  lignes sur l'écran principal, comme en mode ligne.
- Le message final (« Configuration enregistrée… ») est écrit sur l'écran principal, après la
  restauration : il reste dans l'historique.

### Clavier

| Touche | Effet |
|---|---|
| ↑ ↓, Tab, Maj+Tab | focus précédent, suivant (en boucle) |
| Début, Fin | premier, dernier |
| 1 à 9 | focus sur l'option de ce numéro (sans valider) |
| Entrée | valider l'option focalisée |
| ? | aide dite et affichée à la place de la description |
| Échap, Ctrl+C | quitter sans rien écrire (setup) ; fermer (F6) |
| ← → | menu F6 : régler la valeur focalisée |

### Voix

| Événement | Phrase dite |
|---|---|
| ouverture d'un écran | question, option focalisée et son état, nombre de choix, rappel « ? pour l'aide » |
| changement de focus | libellé court et état, par exemple « Gemma 4 E2B, recommandé » |
| option bloquée validée | « Qwen 3 8B : hors de portée de cette machine. Choisissez une autre option. » |
| Échap | « Configuration abandonnée, rien n'est écrit. » |

Le logo n'est jamais dit.

### Menu F6

- Écran alternatif, comme avant, mais curseur visible sur l'élément focalisé et mise à jour
  partielle : un mouvement réécrit la description et deux lignes ; un réglage réécrit sa ligne.
  Changement de niveau (Réglages, Retour) et redimensionnement : redessin complet.
- Mode ligne (mêmes règles de repli) : écran alternatif, effacé une fois à l'ouverture pour
  partir du haut, puis ajout seul : chaque phrase dite s'écrit sur sa ligne (« Répéter »), sans
  autre effacement ni déplacement du curseur. Sous `TERM=dumb`, aucune séquence : les lignes
  s'ajoutent à l'écran du shell, « Menu fermé. » compris. À la fermeture, l'écran du shell
  revient intact et la sortie du shell accumulée pendant le menu est relayée.

## 4. Mise en œuvre et preuves

| Élément | Fichier |
|---|---|
| choix du mode, sondes, touches, modèle, rendu, boucle | `src/steph/tui.py` |
| déroulé du setup plein écran | `src/steph/setup_tui.py` ; `setup.apply_plan`, `setup._main_tui` |
| menu F6 : description, touches rapides, rendu partiel | `src/steph/menu.py`, `src/steph/proxy.py` |
| réglage `ui` (`auto`, `line`, `tui`), surchargé par `STEPH_UI` | `src/steph/config.py` |
| tests | `tests/test_tui.py`, `tests/test_setup_tui.py`, `tests/test_menu.py`, `tests/test_menu_proxy.py` |
| rejeu en pseudo-terminal et captures | une note interne (non publiée), `f6_driver.py` |

Rejeu (`uv run python `) : vrai `steph setup` du début à
l'enregistrement, et vrai proxy steph autour de bash pour F6 (voix journalisée, pas jouée).
Les fichiers `*.steps.txt` donnent, touche par touche, les octets écrits, les lignes effacées
et la position du curseur : un mouvement efface 5 lignes (3 de description, 2 d'options), un
réglage 1, sans jamais effacer l'écran ; le mode ligne n'efface rien après l'ouverture.

Limites connues :

- pyte n'applique pas la couleur de fond aux cellules effacées : sur les PNG, le noir ne couvre
  que les lignes écrites. Un vrai terminal peint tout l'écran.
- Aucun essai avec VoiceOver, Orca ou Speakup réels : le comportement sous lecteur d'écran
  est le mode ligne, prouvé en pseudo-terminal, pas écouté.
- Un redimensionnement pendant un redessin partiel peut entrelacer deux écritures ; le redessin
  complet qui suit remet l'écran d'aplomb.

## Sources

- Sampath H., Merrick A., Macvean A., *Accessibility of Command Line Interfaces*, CHI 2021 :
  https://dl.acm.org/doi/10.1145/3411764.3445544 et https://research.google/pubs/accessibility-of-command-line-interfaces/
- xogium, *The text mode lie: why modern TUIs are a nightmare for accessibility* :
  https://xogium.me/the-text-mode-lie-why-modern-tuis-are-a-nightmare-for-accessibility ;
  résumé OSnews : https://www.osnews.com/story/144892/the-text-mode-lie-why-modern-tuis-are-a-nightmare-for-accessibility/
- AFixt, *Accessible by Design: Improving Command Line Interfaces for All Users* :
  https://afixt.com/accessible-by-design-improving-command-line-interfaces-for-all-users/
- croft, issue #621 (mode lecteur d'écran, curseur réel sur le texte focalisé) :
  https://github.com/vitali87/croft/issues/621
- stablyai/orca, issue #19670 (terminal invisible aux lecteurs sans mode dédié) :
  https://github.com/stablyai/orca/issues/19670
- Ubuntu Wiki, *Accessibility/doc/Speakup* : https://wiki.ubuntu.com/Accessibility/doc/Speakup
- vinux-support, *Using CLI programs with speakup and braille* :
  https://groups.google.com/g/vinux-support/c/XiGwNFMuTo8/m/ltbdsQByrZkJ
- Debian Wiki, *DebianInstaller/Accessibility* : https://wiki.debian.org/DebianInstaller/Accessibility ;
  manuel d'installation §5.2 : https://www.debian.org/releases/stable/amd64/ch05s02
- Debian Wiki, *Accessibility/Orca* : https://wiki.debian.org/Accessibility/Orca ;
  orca-list, octobre 2021 : https://mail.gnome.org/archives/orca-list/2021-October/msg00021.html
- Apple, *Display or hide the alternate screen in Terminal on Mac* :
  https://support.apple.com/guide/terminal/display-or-hide-the-alternate-screen-trmld1f46097/mac
- AppleVis, forums Terminal et VoiceOver :
  https://www.applevis.com/forum/macos-mac-apps/how-can-you-even-use-terminal-daily-macos-voiceover-major-bugs-vim ;
  https://www.applevis.com/forum/macos-mac-apps/how-get-better-experience-terminal-voiceover
- clig.dev : https://clig.dev ; NO_COLOR : https://no-color.org

Limites de la recherche : l'article ACM et les fils AppleVis ont refusé la lecture directe
(403) ; leur contenu cité vient des résumés et extraits des moteurs de recherche. La clé
`voiceOverOnOffKey` n'est documentée par Apple nulle part ; elle a été observée sur ce Mac
(`0`, VoiceOver éteint), d'où la sonde de processus en premier.
