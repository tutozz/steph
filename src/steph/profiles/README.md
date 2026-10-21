# Profils matériels

`steph` adapte les réglages de `llama-server` (parallélisme, taille de batch,
flash attention, type de cache…) au GPU détecté sur la machine. Un profil est
un petit fichier `.toml` dans ce dossier.

## Comment ça marche

Au démarrage du serveur (`steph`, `steph server start`), si `hardware_profile`
vaut `"auto"` (valeur par défaut dans `Config`) :

1. `hardware.py` lance `llama-bench --list-devices` (voisin de `llama-server`)
   et lit les GPU disponibles (Vulkan, CUDA ou Metal). Résultat mis en cache
   dans `$XDG_RUNTIME_DIR/steph/hardware.json`, invalidé si le chemin de
   `llama-server` change. Aucun GPU trouvé → profil `cpu.toml`.
2. `profile.py` choisit le fichier `.toml` dont `[match]` correspond le mieux
   à ce GPU : `pci_ids` (poids 8) > `name` (4) > `vendor` (2) > `kind` (1). À
   score égal, un GPU dédié l'emporte sur un GPU intégré.
3. Les valeurs de `[settings]` du profil retenu s'appliquent, puis
   `~/.config/steph/config.toml`, puis les variables `STEPH_*` (chacune peut
   toujours tout re-surcharger).

`hardware_profile = "none"` désactive complètement la détection et les
profils (comportement d'avant cette fonctionnalité). Une valeur comme
`hardware_profile = "gpu/intel-arc-140t"` force un profil précis, sans
détection.

`steph profile` affiche les GPU détectés, le profil retenu et la commande
`llama-server` qui serait lancée : c'est l'outil de diagnostic à utiliser.

## Contribuer un profil

Ta carte n'a pas de fichier dédié (elle tombe sur `integrated.toml`,
`dedicated.toml` ou `apple.toml`, les profils génériques) ? Contribue les
valeurs mesurées sur ta machine :

1. `steph profile` pour voir le `vendor`, le `kind` et le `pci_id` (Linux) ou
   le nom (Vulkan/Metal) de ta carte.
2. Copie un profil générique proche (`integrated.toml` pour un GPU intégré,
   `dedicated.toml` pour une carte dédiée) vers `gpu/<vendeur>-<modèle>.toml`,
   par exemple `gpu/amd-780m.toml`.
3. Renseigne `[match]` : `pci_ids` si tu l'as (le plus fiable, surtout sur
   Vulkan où le nom est parfois générique), sinon `vendor` + `name` (glob,
   insensible à la casse) ou `vendor` + `kind`.
4. Mesure avec `bench/bench.py` en faisant varier `llm_parallel`, `llm_batch`,
   `llm_ubatch`, `llm_flash_attn`, `llm_cache_type` dans `[settings]`.
5. Ouvre une pull request avec, en commentaire dans le fichier, les chiffres
   avant/après (latence du premier token, latence totale).

## Format d'un profil

```toml
# Nom de la carte, backend utilisé (Vulkan/CUDA/Metal)
[match]
kind = "integrated"        # optionnel : cpu | integrated | dedicated | apple
vendor = "intel"           # optionnel : intel | amd | nvidia | apple | other
pci_ids = ["8086:7d51"]    # optionnel, le plus fiable sur Linux
name = "*RTX 3060*"        # optionnel, glob insensible à la casse sur le nom rapporté

[settings]                 # n'importe quel champ de Config (voir config.py)
llm_ubatch = 512
```
