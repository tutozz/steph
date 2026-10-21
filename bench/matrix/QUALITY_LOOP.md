# Boucle qualité des petits modèles

Objectif : amener un petit modèle rapide (moins de 1 milliard de paramètres) au plancher de qualité
de steph, pour les machines sans GPU (vieux portable i5-7200U). La vitesse de ces modèles est déjà
connue ; ici on ne mesure que la **qualité**, qui ne dépend pas de la machine.

## Cible

- **Plancher** : `tune` ≥ 80 % ET `holdout` ≥ 75 %, avec 0 interdit touché (déjà pénalisé par le barème).
- Modèles visés, par ordre d'intérêt : Qwen3.5 0.8B Q4_K_M, LFM2.5 350M, Granite 4.0 H 350M,
  Luth-LFM2 350M (affiné français), Gemma 3 270M, Qwen3 0.6B.
- Départ (Mac, 800 caractères, barème nettoyé) : Qwen3.5 0.8B 69 % avec `cases_p1.json` ;
  LFM2.5 350M 58 % et Granite 4.0 H 350M 53 % avec `cases_p2.json` ; Gemma 3 270M 31 %.

## Outils

- `bench_run.py` : `--cases <fichier>`, `--maxc 800|1500|0`, `--payload '<json>'` (fusionné dans
  chaque requête : `grammar`, `temperature`, `stop`, `repeat_penalty`, `n_predict`...). Un cas peut
  aussi porter son propre `"payload"`.
- `make_cases.py` et `variants.py` : exemples de génération de cas. Crée tes propres fichiers de cas
  dans `quality/<axe>/`, jamais en modifiant `cases.json`, `cases_p1.json`, `cases_p2.json`.
- `score.py <résultat>` : donne `quality` (brut), `quality_cleaned`, `tune` et `holdout` (nettoyés).
  Le nettoyage (`clean`) retire balises de raisonnement, blocs de code et échos, puis joint les lignes.

## Règles, à respecter à chaque essai

- **Choisir uniquement sur `tune`.** `holdout` ne sert qu'à vérifier à la fin : ne l'utilise jamais
  pour comparer deux variantes, sinon le réglage colle au banc et décevra en vrai.
- **Prompts génériques** : ne cite aucune commande, valeur ou fait du banc (pas de Header.tsx, pas de
  192.168..., pas de « 9 conteneurs »). Les exemples utilisent des commandes absentes du banc.
- **Rien dans `src/steph/`** : on explore ici ; l'intégration dans steph viendra après.
- Un essai = un résultat JSON dans `results/quality/<axe>/`, label `q-<axe>-<modèle>-<variante>`,
  et une ligne dans `results/quality/<axe>/journal.tsv` :
  `essai	modèle	variante (description courte)	tune	holdout	note`.
- Aucune opération git. Français accentué, sans emoji ni tiret cadratin.
- Anti-blocage : aucune commande de plus de 4 minutes ; boucles longues en arrière-plan, suivies par
  appels courts.

## Machines et ports

| Machine | Axe | Port | Serveur | Modèles |
|---|---|---|---|---|
| Mac | A prompt | 8860 | `/opt/homebrew/bin/llama-server --ngl 99` | scratchpad `models/` ; garder 2 Go libres ; supprimer après usage |
| Mac | B décodage | 8865 | idem | idem |
| homelab | C entrée | 8870 | `/root/stephbench-matrix/bin/vulkan/llama-b11205/llama-server --ngl 99` | `/mnt/backup-hdd/stephbench-tmp/models/` |
| homelab | D modèles | 8875 | idem | idem |

homelab : aucune commande qm, pct, pvesm, aucun apt, aucune VM touchée ; dossiers autorisés
`/root/stephbench-matrix` et `/mnt/backup-hdd/stephbench-tmp` ; préfixe `nice -n 19`. Deux serveurs
sur le même GPU sont acceptés ici (on ne mesure pas la vitesse). Ne touche pas au llama-server de
l'utilisateur sur le Mac (port 8765).

## Rapport attendu

Pour chaque modèle visé : meilleure recette (fichier de cas, `--maxc`, `--payload`), `tune`,
`holdout`, et 3 sorties typiques. Puis ce que chaque levier a apporté, et ce qui n'a pas été vérifié.
