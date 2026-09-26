# Rendre steph viral : analyse des dépôts en tendance et plan d'action

Recherche du 2026-09-26. Sources : GitHub trending (jour, semaine, mois), 12 README,
7 pages d'accueil d'outils viraux, guides de lancement 2024-2026. Les nombres d'étoiles
sont ceux affichés par GitHub au moment de la recherche ; ils n'ont pas été recoupés.

## 1. Ce que font les dépôts qui montent

| Dépôt | Étoiles | Accroche | Démo | Install en 1 ligne |
|---|---|---|---|---|
| [debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio) | ~35,7k | « Open-source voice cloning […] in 646 languages. » | GIF + captures | oui, `curl \| sh` |
| [AlexsJones/llmfit](https://github.com/AlexsJones/llmfit) | ~37,2k | « Find out which open-source LLMs your hardware can comfortably run. » | `demo.gif` du TUI | oui |
| [bilawalsidhu/gods-eye-view](https://github.com/bilawalsidhu/gods-eye-view) | ~43,4k | « A spy-satellite simulator in your browser — then you realize the sources are public and the data is real. » | GIF + YouTube | oui |
| [max-sixty/worktrunk](https://github.com/max-sixty/worktrunk) | ~8,4k | « A CLI for git worktree management, designed for running AI agents in parallel. » | aucune | oui |
| [akitaonrails/ai-memory](https://github.com/akitaonrails/ai-memory) | ~8,4k | « Quit Claude Code mid-task, start Codex […] continue without re-explaining. » | aucune | oui |
| [CapSoftware/Cap](https://github.com/CapSoftware/Cap) | ~22,8k | « Beautiful, shareable screen recordings. » | capture pleine largeur | non |
| [k2-fsa/OmniVoice](https://github.com/k2-fsa/OmniVoice) | ~13,9k | « Massively multilingual zero-shot TTS […] 600 languages. » | liens HF / Colab | non |

Pages d'accueil étudiées : [Bun](https://bun.sh), [uv](https://docs.astral.sh/uv/),
[Ollama](https://ollama.com), [Zed](https://zed.dev), [Warp](https://www.warp.dev),
[Open WebUI](https://openwebui.com), [Wispr Flow](https://wisprflow.ai).

### Motifs récurrents, du plus au moins corrélé à la croissance

1. **Accroche = résultat, pas mécanisme.** llmfit dit ce que vous saurez, pas comment il calcule.
2. **Un chiffre dans l'accroche.** « 646 languages », « 10-100x faster than pip », « 9M+ developers ».
3. **Démo avant la doc.** GIF ou vidéo dans les 15 premières lignes du README.
4. **Installation en une commande**, copiable, juste sous l'accroche.
5. **Preuve sociale externe** : badge Trendshift, rang Product Hunt, « vu 5M fois sur YouTube ».
6. **Note datée du mainteneur** en tête (worktrunk : « September 2026: … »). Elle remplace la roadmap.
7. **Scénario vécu** plutôt que douleur abstraite (ai-memory).
8. **Positionnement en une ligne** : « l'alternative à X, mais Y » (Cap vs Loom).
9. **Audio avant/après** pour les outils voix (Wispr Flow : dictée brute, puis texte propre).
10. **README traduits** dès le départ (llmfit EN/ZH/JA).

**Espace libre repéré :** aucun des 12 dépôts ne résout la démo **non visuelle**. Un GIF muet
ne dit rien à un développeur aveugle. steph peut être le premier à mettre une démo audio
dans son README.

## 2. État actuel de steph

| Critère | Aujourd'hui | Écart |
|---|---|---|
| Accroche | « Your terminal, out loud » | **point fort**, à garder |
| Sous-titre du site | annonce « français seulement » dès le hero | aucun projet viral ne commence par une limite |
| Démo sur le site | 4 extraits audio jouables | bon, format cohérent avec le produit |
| Démo dans le README | **aucune** ; lien vers le site | le visiteur GitHub n'entend rien |
| Installation | `git clone` + script + `uv`, ~3 Go | 3 étapes contre 1 chez Bun, Ollama, VoiceStudio |
| Chiffre d'accroche | absent du hero | la latence mesurée existe déjà dans le README |
| Preuve sociale | 0 étoile, pas de métrique | normal au lancement, à construire |
| Licence sur GitHub | détectée « Other / NOASSERTION » | à anticiper, voir §4 |
| Description du dépôt | en français | le trending et HN lisent l'anglais |
| Langue de la voix | français seulement | **frein n°1** pour HN, Reddit, Product Hunt |

## 3. Plan d'action, par levier

### A. Le README devient la page d'accueil (impact fort, effort faible)

- **Vidéo avec son juste sous la bannière.** GitHub lit les `.mp4` déposés en pièce jointe
  (`user-attachments`) avec le son, en un clic. 30 à 45 s, écran noir, on entend steph
  annoncer un `npm run build` qui casse, puis la correction. Le concept : **« écran éteint »**.
  Il prouve le produit sans image et il se partage seul.
- **Alt text et transcription** sous la vidéo : le public cible lit le README au lecteur d'écran.
- **Scénario vécu en 2 lignes**, sur le modèle d'ai-memory :
  > Your build fails. A screen reader reads you 400 lines of stack trace.
  > steph says: "TypeScript error: property titel does not exist, use title."
- **Un chiffre** dans le premier écran : « ~1 s to answer a question about your whole session,
  on a 4 GB GPU, nothing leaves the machine ». Chiffre déjà mesuré dans le README.
- **Description du dépôt en anglais**, avec les topics existants (`accessibility`,
  `screen-reader`, `visually-impaired`) plus `tts`, `llama-cpp`, `local-llm`, `terminal`.
- **Note datée du mainteneur** en blockquote, une ligne : où en est steph, ce qui arrive.

### B. Réduire la friction d'installation (impact fort, effort moyen)

- Installateur en une ligne : `curl -fsSL https://steph.lsmdx.com/install | sh`,
  qui clone et lance `scripts/install.sh`. Afficher « ~3 GB, ~5 min » à côté, honnêtement.
- Plus tard : formule Homebrew (`brew install tutozz/tap/steph`), le chemin attendu sur macOS.

### C. La voix anglaise (impact décisif, effort à évaluer)

HN, Reddit, Product Hunt et le trending sont anglophones. Une voix française seulement
réduit la démo à un public francophone. Deux ordres possibles :

| Option | Pour | Contre |
|---|---|---|
| Lancer d'abord en France, puis l'international avec la voix anglaise | canaux FR accessibles tout de suite, premiers retours réels | le pic HN arrive plus tard |
| Voix anglaise avant tout lancement | un seul grand lancement, audience maximale | retarde tout |

**Décision (2026-09-26) :** voix anglaise d'abord, puis un seul grand lancement. Aucun canal
public avant. Un seul Show HN possible : ne pas le brûler.

### D. Site steph.lsmdx.com (impact moyen, effort faible)

- Retirer « French only » du sous-titre ; le mettre dans la section install ou une FAQ.
- Bouton **« Hear it »** dans le hero, lecture immédiate de l'extrait le plus fort (l'erreur de build).
- Commande d'installation copiable dans le hero, pas seulement plus bas.
- FAQ « Why not open source? » (voir §4).

### E. Preuve sociale sans témoignage

La règle du projet interdit toute citation de testeur : seule la mention « conçu et testé
avec des personnes malvoyantes » est autorisée. La preuve sociale passe donc par :

- chiffres mesurés (latence, taille du modèle, GPU minimal) ;
- badges externes gagnés au lancement (Trendshift, Product Hunt, « vu sur LinuxFr ») ;
- la vidéo « écran éteint », qui prouve au lieu de raconter.

## 4. La licence sur HN : préparer la réponse avant de poster

HN surveille les licences « source available » ([#31658939](https://news.ycombinator.com/item?id=31658939),
[#46213709](https://news.ycombinator.com/item?id=46213709)). Critique type : trop long à comprendre.

- Ne jamais écrire « open source », nulle part. Écrire « source available, free for personal use ».
- Premier commentaire du Show HN, rédigé à l'avance : 3 lignes. Gratuit pour les personnes,
  licence payante pour les entreprises, pourquoi (financer le travail d'accessibilité).
- Le badge licence reste, mais une ligne explicite accompagne le README (le badge seul ne dit rien).

## 5. Calendrier de lancement

| Étape | Canal | Condition | Note |
|---|---|---|---|
| 0 | README + vidéo + installateur | aucune | prérequis de tout le reste |
| 1 | Voix anglaise | aucune | **bloque toutes les étapes suivantes** |
| 2 | LinuxFr.org, Journal du hacker, Korben, communautés malvoyantes FR | voix anglaise prête | même semaine que le Show HN |
| 3 | Awesome lists : `awesome-accessibility`, `awesome-cli-apps`, `awesome-selfhosted` | README en anglais | trafic durable, faible effort |
| 4 | Show HN, mardi-jeudi 15h-18h heure de Paris | **voix anglaise** | titre < 80 caractères, ton neutre |
| 5 | r/Blind, AppleVis, r/commandline, r/LocalLLaMA | idem | jamais demander d'étoile |
| 6 | Product Hunt, newsletters (Console.dev, TLDR, Changelog) | badges des étapes 1-5 | réutiliser la vidéo |
| 7 | CSUN, Innovation Track (mars, Anaheim) | voix anglaise | vérifier les dates 2027 |

Titre Show HN retenu (mention neutre imposée, « built with blind developers » refusé) :
- `Show HN: Steph - a terminal that tells you what matters, out loud (local LLM)`

## 6. Non vérifié

- Ghostty : page non récupérée.
- Procédures de soumission Console.dev, Changelog, TLDR : non trouvées.
- Aucun cas daté de lancement d'un outil comparable sur LinuxFr, Journal du hacker ou r/Blind.
- Chiffres « 1000+ étoiles en un jour » pour un Show HN : affirmation des guides cités, pas une mesure.
- Dates CSUN 2027 : seule l'édition 2026 (9-13 mars) a été vue.

## 7. Appliqué le 2026-09-26

| Élément | Fichier |
|---|---|
| Installateur en une ligne | `site/public/install` |
| Hero : bouton « Hear it », commande `curl`, « French only » retiré du sous-titre | `site/public/en/index.html`, `site/public/index.html`, `site/public/main.js` |
| Libellés « Sans / Avec steph » traduits sur la page EN | `site/public/en/index.html` |
| Ligne « pourquoi pas open source » | idem |
| README : scénario, chiffre, note datée, install en une ligne | `README.md`, `README.fr.md` |

Reste : vidéo « écran éteint » dans le README, voix anglaise, formule Homebrew.
