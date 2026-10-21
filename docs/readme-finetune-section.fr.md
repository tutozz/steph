<!--
Brouillon de section pour README.fr.md. Chaque chiffre vient de docs/readme-charts/data.json.
Les chiffres « placeholder » de data.json sont suivis d'un commentaire HTML « ph: <clé> » et
se mettent à jour après le banc du modèle affiné ; lancer ensuite python3 docs/readme-charts/build.py.
-->

## Un modèle de voix assez petit pour n'importe quel portable

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/charts/hero.fr.dark.png">
  <img src="assets/charts/hero.fr.light.png" alt="Le petit modèle de steph : presque la qualité d'un modèle 9B, la taille d'un modèle 270M" width="100%">
</picture>

steph transforme un mur de sortie de terminal en une phrase dite à voix haute. Jusqu'ici, une bonne phrase demandait un gros modèle : Qwen3.5 9B donne 100 % des faits attendus sur notre banc de 36 vraies sorties de terminal. Ce modèle pèse 5 681 Mo. Sur un vieux portable sans GPU, il est hors de portée.

Les petits modèles bruts tiennent, mais ils ratent l'essentiel. Sous le milliard de paramètres, ils obtiennent entre 13,3 % et 46,7 % au même banc, et le meilleur, prompt réglé, plafonne à 68,3 % sur le jeu de contrôle.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/charts/quality.fr.dark.png">
  <img src="assets/charts/quality.fr.light.png" alt="Qualité au banc : Qwen3.5 9B 100 %, Gemma 4 E2B 97,5 %, steph affiné (provisoire), petits modèles bruts entre 13,3 % et 46,7 %" width="100%">
</picture>

Alors on a entraîné le nôtre. Le petit modèle de steph apprend du 9B, sur de vraies sessions de terminal, à dire ce que dirait le 9B, dans un fichier assez petit pour n'importe quel portable.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/charts/example.fr.dark.png">
  <img src="assets/charts/example.fr.light.png" alt="Avant, après sur rm /etc/hostname : le petit modèle brut parle de Header.tsx, un fichier absent de la sortie ; steph dit que la suppression a échoué faute de permission" width="100%">
</picture>

La cible : un portable Intel Core i5-7200U de 2017<!-- ph: laptop.year -->, 2 cœurs, sans GPU. Là, steph dit son premier mot en moins de 1,5 s<!-- ph: ttft_p90_i5.steph --> neuf fois sur dix, quand un modèle 2B met 13,3 s.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/charts/speed.fr.dark.png">
  <img src="assets/charts/speed.fr.light.png" alt="Premier mot sur i5-7200U sans GPU : steph 1,5 s (provisoire), Qwen3.5 0.8B 5,7 s, Qwen3.5 2B 13,3 s, SmolLM3 3B 22,4 s, Ministral 3 3B 27,0 s" width="100%">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/charts/size.fr.dark.png">
  <img src="assets/charts/size.fr.light.png" alt="Taille sur disque : steph 292 Mo (provisoire), Gemma 4 E2B 3 350 Mo, Qwen3.5 9B 5 681 Mo" width="100%">
</picture>

**Comment on l'a fait.** De vraies sorties de terminal recueillies sur 7<!-- ph: corpus.machines --> machines du labo, anonymisées et auditées avant tout usage ; chacune étiquetée par Qwen3.5 9B (distillation) ; un affinage LoRA d'un petit modèle de base ; un export GGUF pour llama.cpp. Méthode complète, seuils et fichiers du banc : le journal de mission interne (non publié)).
