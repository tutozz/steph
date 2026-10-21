#!/usr/bin/env python3
"""Fusionne base + moyenne des adaptateurs SFT + moyenne des adaptateurs de préférences (P16).

    python3 merge_pref.py --base <dossier HF> --out <dossier> --sft a1 a2 ... --pref p1 p2 ...

Même arithmétique que vocab/granite_rebuild_soup.py : deltas (B @ A) * alpha / r en float32,
somme sur les poids de base en float32, puis bfloat16. Recopie config.json et le tokenizer de la
base, comme l'exige la conversion GGUF de Granite.

SPDX-License-Identifier: MIT
"""

import argparse
import json
import shutil
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file


def mean_deltas(folders):
    acc = {}
    for folder in folders:
        cfg = json.load(open(Path(folder) / "adapter_config.json"))
        assert not cfg.get("use_rslora") and not cfg.get("use_dora") and not cfg.get("fan_in_fan_out")
        scale = cfg["lora_alpha"] / cfg["r"]
        sd = load_file(str(Path(folder) / "adapter_model.safetensors"))
        for k in sd:
            if k.endswith("lora_A.weight"):
                name = k.replace("base_model.model.", "", 1).replace(".lora_A.weight", ".weight")
                acc[name] = acc.get(name, 0) + (sd[k.replace("lora_A", "lora_B")].float() @ sd[k].float()) * scale
    return {k: v / len(folders) for k, v in acc.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sft", nargs="+", required=True)
    ap.add_argument("--pref", nargs="*", default=[])
    # R1 : interpolation vers la base (task arithmetic), 1.0 = fusion complète
    ap.add_argument("--sft-scale", type=float, default=1.0)
    ap.add_argument("--pref-scale", type=float, default=1.0)
    a = ap.parse_args()
    base_dir, out_dir = Path(a.base), Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = load_file(str(base_dir / "model.safetensors"))
    deltas = [(mean_deltas(a.sft), a.sft_scale)] + ([(mean_deltas(a.pref), a.pref_scale)] if a.pref else [])
    for d, _ in deltas:
        missing = set(d) - set(base)
        assert not missing, sorted(missing)[:3]
    out = {}
    for name, w in base.items():
        w = w.float()
        for d, scale in deltas:
            if name in d:
                w = w + scale * d[name]
        out[name] = w.to(torch.bfloat16).contiguous()
    save_file(out, str(out_dir / "model.safetensors"), metadata={"format": "pt"})
    for f in base_dir.iterdir():
        if f.name != "model.safetensors" and f.is_file() and not f.name.endswith((".sig", ".md")):
            shutil.copy(f, out_dir / f.name)
    print(f"{len(a.sft)} adaptateurs SFT, {len(a.pref)} de préférences, {len(out)} tenseurs écrits")


if __name__ == "__main__":
    main()
