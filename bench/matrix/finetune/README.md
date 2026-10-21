# Étiquetage par l'enseignant (Qwen3.5 9B)

`label.py` construit les messages exactement comme steph (`src/steph/digest.py` +
`src/steph/prompts.py`), interroge un llama-server local et écrit les paires
d'entraînement. Reprise automatique sur interruption.

## Lancement sur homelab (RTX 3060, build vulkan — pas de build CUDA disponible)

Serveur, 4 slots :

```
ssh homelab
nohup nice -n 19 /root/stephbench-matrix/bin/vulkan/llama-b11205/llama-server \
  -m /mnt/backup-hdd/stephbench-tmp/models/Qwen3.5-9B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8890 -c 8192 -ngl 99 --parallel 4 \
  --no-webui --jinja --reasoning-budget 0 -b 512 -ub 512 \
  > server.log 2>&1 &
```

Étiquetage d'un corpus brut (cmd, exit, duration, output) :

```
PYTHONPATH=<dossier contenant le paquet steph vendorisé> python3 label.py \
  --in corpus.jsonl --out corpus.labeled.jsonl --port 8890 --parallel 4
```

Validation sur les cas du banc (messages déjà construits par `make_cases.py`,
scorable directement par `score.py`) :

```
PYTHONPATH=<idem> python3 label.py \
  --cases ../cases.json --out results_cases.json --port 8890 --parallel 4
python3 ../score.py results_cases.json
```

`label.py` importe `steph.digest`, `steph.prompts`, `steph.textproc` et
`score.clean` (bench/matrix/score.py) : sur une machine sans le dépôt complet,
copier ces fichiers et pointer `PYTHONPATH` dessus (voir déploiement fait sur
homelab : `/root/stephbench-matrix/label/{steph/,matrix/}`).

## Réglage retenu : `--presence-penalty 1.0`

À température 0 (imposée pour des étiquettes reproductibles), le greedy pur part
parfois en énumération complète d'une liste au lieu de suivre la consigne
« 3 noms au plus » du prompt système (cas fx18 du banc). Une pénalité de
présence de 1.0 corrige ce mode dégénéré sans réintroduire d'aléatoire. C'est
la valeur par défaut de `label.py`.

## Rejets

Une étiquette est rejetée (écrite dans `<out>.rejects.jsonl`, pas dans `<out>`)
si le texte brut contient `<think>`, si le texte nettoyé (`score.clean`) est
vide, ou dépasse 25 mots.

## Licence

Ces scripts d'entraînement et de préparation du corpus sont sous [MIT](LICENSE),
comme le code du banc (`benchmark/`). Le reste du dépôt steph reste sous PolyForm
Noncommercial (voir [../../../LICENSE.md](../../../LICENSE.md)).
