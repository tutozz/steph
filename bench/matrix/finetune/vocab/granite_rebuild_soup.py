"""granite_rebuild_soup.py <base_hf> <sortie> <adaptateur1> [...] : soupe uniforme reconstruite hors GPU.

Même arithmétique que soup/soup.py : delta = (B @ A) * alpha / r en float32, moyenne des deltas,
ajout aux poids de base en float32, puis tout le modèle en bfloat16. Le f16 de la soupe ayant été
supprimé sur rtx3080, c'est le seul moyen de repartir d'un GGUF non quantifié.

SPDX-License-Identifier: MIT
"""
import json
import shutil
import sys
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file

base_dir, out_dir, adapters = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
out_dir.mkdir(parents=True, exist_ok=True)
base = load_file(str(base_dir / "model.safetensors"))
acc = {}
for folder in adapters:
    cfg = json.load(open(Path(folder) / "adapter_config.json"))
    assert not cfg.get("use_rslora") and not cfg.get("use_dora") and not cfg.get("fan_in_fan_out")
    scale = cfg["lora_alpha"] / cfg["r"]
    sd = load_file(str(Path(folder) / "adapter_model.safetensors"))
    n = 0
    for k in sd:
        if not k.endswith("lora_A.weight"):
            continue
        name = k.replace("base_model.model.", "", 1).replace(".lora_A.weight", ".weight")
        assert name in base, name
        d = (sd[k.replace("lora_A", "lora_B")].float() @ sd[k].float()) * scale
        acc[name] = acc.get(name, 0) + d
        n += 1
    print(f"{folder} : {n} matrices", flush=True)
out = {}
for name, w in base.items():
    w = w.float()
    if name in acc:
        w = w + acc[name] / len(adapters)
    out[name] = w.to(torch.bfloat16).contiguous()
save_file(out, str(out_dir / "model.safetensors"), metadata={"format": "pt"})
for f in base_dir.iterdir():
    if f.name != "model.safetensors" and f.is_file() and not f.name.endswith((".sig", ".md")):
        shutil.copy(f, out_dir / f.name)
print(f"{len(acc)} matrices modifiées sur {len(base)} tenseurs")
